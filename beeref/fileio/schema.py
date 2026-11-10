USER_VERSION = 3
APPLICATION_ID = 2060242126


SCHEMA = [
    """
    CREATE TABLE items (
        id INTEGER PRIMARY KEY,
        type TEXT NOT NULL,
        x REAL DEFAULT 0,
        y REAL DEFAULT 0,
        z REAL DEFAULT 0,
        scale REAL DEFAULT 1,
        rotation REAL DEFAULT 0,
        flip INTEGER DEFAULT 1,
        data JSON,
        parent_id INTEGER DEFAULT NULL,
        sort_order REAL DEFAULT NULL
    )
    """,
    """
    CREATE TABLE sqlar (
        name TEXT PRIMARY KEY,
        item_id INTEGER NOT NULL UNIQUE,
        mode INT,
        mtime INT default current_timestamp,
        sz INT,
        data BLOB,
        FOREIGN KEY (item_id)
          REFERENCES items (id)
             ON DELETE CASCADE
             ON UPDATE NO ACTION
    )
    """,
]


MIGRATIONS = {
    2: [
        "ALTER TABLE items ADD COLUMN data JSON",
        "UPDATE items SET data = json_object('filename', filename)",
    ],
    # Version 3: Hierarchy support. ``parent_id`` references the
    # ``items.id`` of the parent item (positions are then relative to
    # the parent); ``sort_order`` is the item's position in the
    # hierarchy among its siblings.
    3: [
        "ALTER TABLE items ADD COLUMN parent_id INTEGER DEFAULT NULL",
        "ALTER TABLE items ADD COLUMN sort_order REAL DEFAULT NULL",
    ],
}
