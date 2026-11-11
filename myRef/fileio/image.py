# This file is part of BeeRef.
#
# BeeRef is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BeeRef is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BeeRef.  If not, see <https://www.gnu.org/licenses/>.

import logging
import os.path
import tempfile
from urllib.error import URLError
from urllib import parse, request

from PyQt6 import QtGui

import exif
from lxml import etree
import plum


logger = logging.getLogger(__name__)


def exif_rotated_image(path=None):
    """Returns a QImage that is transformed according to the source's
    orientation EXIF data.
    """

    img = QtGui.QImage(path)
    if img.isNull():
        return img

    with open(path, 'rb') as f:
        try:
            exifimg = exif.Image(f)
        except (plum.exceptions.UnpackError, NotImplementedError):
            logger.exception(f'Exif parser failed on image: {path}')
            return img

    try:
        if 'orientation' in exifimg.list_all():
            orientation = exifimg.orientation
        else:
            return img
    except (NotImplementedError, ValueError):
        logger.exception(f'Exif failed reading orientation of image: {path}')
        return img

    transform = QtGui.QTransform()

    if orientation == exif.Orientation.TOP_RIGHT:
        return img.mirrored(horizontal=True, vertical=False)
    if orientation == exif.Orientation.BOTTOM_RIGHT:
        transform.rotate(180)
        return img.transformed(transform)
    if orientation == exif.Orientation.BOTTOM_LEFT:
        return img.mirrored(horizontal=False, vertical=True)
    if orientation == exif.Orientation.LEFT_TOP:
        transform.rotate(90)
        return img.transformed(transform).mirrored(
            horizontal=True, vertical=False)
    if orientation == exif.Orientation.RIGHT_TOP:
        transform.rotate(90)
        return img.transformed(transform)
    if orientation == exif.Orientation.RIGHT_BOTTOM:
        transform.rotate(270)
        return img.transformed(transform).mirrored(
            horizontal=True, vertical=False)
    if orientation == exif.Orientation.LEFT_BOTTOM:
        transform.rotate(270)
        return img.transformed(transform)

    return img


#: Maximum number of images imported from a single web page
MAX_PAGE_IMAGES = 100
#: Images from web pages smaller than this (in both dimensions) are
#: skipped; they are usually icons, avatars or tracking pixels.
MIN_PAGE_IMAGE_SIZE = 64
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp',
                    '.tif', '.tiff', '.svg', '.avif')


def _largest_from_srcset(srcset):
    """The URL with the highest width/density from a ``srcset``."""

    best = None
    best_size = -1
    for candidate in srcset.split(','):
        parts = candidate.strip().split()
        if not parts:
            continue
        size = 1
        if len(parts) > 1:
            try:
                size = float(parts[1][:-1])
            except ValueError:
                pass
        if size > best_size:
            best, best_size = parts[0], size
    return best


def image_urls_from_html(html, base_url):
    """All image URLs referenced in a web page, without duplicates and
    in the order of appearance."""

    try:
        root = etree.HTML(html)
    except (etree.LxmlError, ValueError):
        return []
    if root is None:
        return []

    found = []
    for meta in root.xpath(
            "//meta[@property='og:image' or @name='twitter:image']"):
        found.append(meta.get('content'))
    for img in root.xpath('//img'):
        srcset = img.get('srcset') or img.get('data-srcset')
        if srcset:
            found.append(_largest_from_srcset(srcset))
        found.append(img.get('data-src') or img.get('src'))
    for link in root.xpath('//a[@href]'):
        href = link.get('href')
        if parse.urlparse(href).path.lower().endswith(IMAGE_EXTENSIONS):
            found.append(href)

    urls = []
    for url in found:
        if not url or url.startswith('data:'):
            continue
        url = parse.urljoin(base_url, url.strip())
        if url not in urls:
            urls.append(url)
    return urls


def _open_url(url):
    req = request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    return request.urlopen(req)


def _image_from_bytes(data):
    with tempfile.TemporaryDirectory() as tmp:
        fname = os.path.join(tmp, 'img')
        with open(fname, 'wb') as f:
            f.write(data)
        return exif_rotated_image(fname)


def load_images_from_url(url, canceled=None):
    """Load an image from a URL. If the URL points to a web page
    instead, load all (not too small) images found on that page.

    :param canceled: Optional callable returning ``True`` to stop
        downloading further images of a page.
    :returns: List of ``(QImage, url)`` tuples; the image may be null
        if nothing could be loaded.
    """

    try:
        response = _open_url(url)
        data = response.read()
        content_type = response.headers.get('Content-Type', '') or ''
    except (URLError, ValueError, OSError) as e:
        logger.debug(f'Downloading {url} failed: {e}')
        return [(exif_rotated_image(), url)]

    img = _image_from_bytes(data)
    if not img.isNull() or 'html' not in content_type.lower():
        return [(img, url)]

    logger.debug(f'{url} is a web page; looking for images')
    results = []
    for img_url in image_urls_from_html(data, url)[:MAX_PAGE_IMAGES]:
        if canceled and canceled():
            break
        try:
            img = _image_from_bytes(_open_url(img_url).read())
        except (URLError, ValueError, OSError) as e:
            logger.debug(f'Downloading {img_url} failed: {e}')
            continue
        if img.isNull() or (img.width() < MIN_PAGE_IMAGE_SIZE
                            and img.height() < MIN_PAGE_IMAGE_SIZE):
            continue
        results.append((img, img_url))
    return results or [(exif_rotated_image(), url)]


def load_image_list(path, canceled=None):
    """Like ``load_image``, but web pages result in all their images.

    :returns: List of ``(QImage, filename or url)`` tuples.
    """

    if isinstance(path, str) or path.isLocalFile():
        return [load_image(path)]
    url = bytes(path.toEncoded()).decode()
    domain = '.'.join(parse.urlparse(url).netloc.split(".")[-2:])
    if domain == 'pinterest.com':
        return [load_image(path)]
    return load_images_from_url(url, canceled)


def load_image(path):
    if isinstance(path, str):
        path = os.path.normpath(path)
        return (exif_rotated_image(path), path)
    if path.isLocalFile():
        path = os.path.normpath(path.toLocalFile())
        return (exif_rotated_image(path), path)

    url = bytes(path.toEncoded()).decode()
    domain = '.'.join(parse.urlparse(url).netloc.split(".")[-2:])
    img = exif_rotated_image()
    if domain == 'pinterest.com':
        try:
            page_data = request.urlopen(url).read()
            root = etree.HTML(page_data)
            url = root.xpath("//img")[0].get('src')
        except Exception as e:
            logger.debug(f'Pinterest image download failed: {e}')
    try:
        imgdata = request.urlopen(url).read()
    except URLError as e:
        logger.debug(f'Downloading image failed: {e.reason}')
    else:
        with tempfile.TemporaryDirectory() as tmp:
            fname = os.path.join(tmp, 'img')
            with open(fname, 'wb') as f:
                f.write(imgdata)
                logger.debug(f'Temporarily saved in: {fname}')
            img = exif_rotated_image(fname)
    return (img, url)
