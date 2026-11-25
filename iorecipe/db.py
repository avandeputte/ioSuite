"""MariaDB access: one short connection per unit of work, and the schema (created at start)."""

from iorecipe import config

from iosuite_shared import db as shared_db

SCHEMA_VERSION = 2  # recorded in rcp_schema_version; the tables are made as SCHEMA says, and get the columns and indexes added to it later (schema.create)
PREFIX = "rcp"

# Every table is rcp_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS rcp_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite_shared, iorecipe/auth.py)
    # owner_id NULL: a family recipe (everyone sees it); otherwise the private recipe of that account.
    # ingredients, steps and tags are JSON lists of strings; a line of ingredients or steps that ends with a colon
    # ("For the icing:") is a heading. Times are minutes. words: everything a search looks in, in lower case.
    # photo: the id in rcp_photos of the picture the cards show (the first of the recipe's own; 0: none).
    """CREATE TABLE IF NOT EXISTS rcp_recipes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        title VARCHAR(255) NOT NULL,
        description TEXT NULL,
        servings VARCHAR(64) NULL,
        prep_minutes INT NULL,
        cook_minutes INT NULL,
        total_minutes INT NULL,
        ingredients MEDIUMTEXT NOT NULL,
        steps MEDIUMTEXT NOT NULL,
        notes TEXT NULL,
        tags TEXT NOT NULL,
        source_url VARCHAR(2048) NULL,
        source_name VARCHAR(255) NULL,
        photo INT NOT NULL DEFAULT 0,
        words MEDIUMTEXT NOT NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_rcp_recipes_owner (owner_id, title)
    )""",
    # the pictures, as JPEG: the picture the page shows and a small one for the cards. step NULL: one of the recipe's
    # own, in the order of position (the first is the one the cards show); otherwise the picture of that step (its
    # place in the recipe's steps, from 0).
    """CREATE TABLE IF NOT EXISTS rcp_photos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        recipe_id INT NOT NULL,
        step INT NULL,
        position INT NOT NULL DEFAULT 0,
        picture MEDIUMBLOB NOT NULL,
        thumb MEDIUMBLOB NOT NULL,
        width INT NOT NULL,
        height INT NOT NULL,
        KEY idx_rcp_photos_recipe (recipe_id, position),
        CONSTRAINT fk_rcp_photos_recipe FOREIGN KEY (recipe_id) REFERENCES rcp_recipes(id) ON DELETE CASCADE
    )""",
    # what one account thinks of a recipe: a favourite or not, and its rating (1 to 5, NULL: none)
    """CREATE TABLE IF NOT EXISTS rcp_marks (
        recipe_id INT NOT NULL,
        user_id INT NOT NULL,
        favourite TINYINT(1) NOT NULL DEFAULT 0,
        rating TINYINT NULL,
        PRIMARY KEY (recipe_id, user_id),
        KEY idx_rcp_marks_user (user_id, favourite),
        CONSTRAINT fk_rcp_marks_recipe FOREIGN KEY (recipe_id) REFERENCES rcp_recipes(id) ON DELETE CASCADE
    )""",
    # cookbooks: owner_id NULL is a family cookbook (everyone sees it, it holds family recipes); otherwise the private
    # cookbook of that account, which may hold the family's recipes and its own
    """CREATE TABLE IF NOT EXISTS rcp_books (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        name VARCHAR(191) NOT NULL,
        description TEXT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_rcp_books_owner (owner_id, name)
    )""",
    """CREATE TABLE IF NOT EXISTS rcp_book_recipes (
        book_id INT NOT NULL,
        recipe_id INT NOT NULL,
        added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (book_id, recipe_id),
        KEY idx_rcp_book_recipes_recipe (recipe_id),
        CONSTRAINT fk_rcp_book_recipes_book FOREIGN KEY (book_id) REFERENCES rcp_books(id) ON DELETE CASCADE,
        CONSTRAINT fk_rcp_book_recipes_recipe FOREIGN KEY (recipe_id) REFERENCES rcp_recipes(id) ON DELETE CASCADE
    )""",
]


# Where the database is, its pool, the transaction nested calls share, q / one / ex / many, the settings table and the
# tables made at start are the suite's (iosuite_shared.db.AppDatabase): a statement on its own is one round trip, tx()
# is one transaction (committed on success, rolled back on error), and q / one / ex inside a `with tx():` block run in it.
_db = shared_db.AppDatabase(config, PREFIX, SCHEMA, SCHEMA_VERSION)
connect, tx, q, one, ex, many = _db.connect, _db.tx, _db.q, _db.one, _db.ex, _db.many
marks = shared_db.marks
get_setting, set_setting = _db.get_setting, _db.set_setting
schema_version, ensure_database, migrate, reset_all = _db.schema_version, _db.ensure_database, _db.migrate, _db.reset_all


def counts() -> dict:
    """What is in the tables (`iosuite iorecipe check`, and the app's diagnostics tool)."""
    return {"recipes": one("SELECT count(*) AS n FROM rcp_recipes")["n"],
            "photos": one("SELECT count(*) AS n FROM rcp_photos")["n"],
            "cookbooks": one("SELECT count(*) AS n FROM rcp_books")["n"],
            "photoBytes": int(one("SELECT COALESCE(SUM(LENGTH(picture) + LENGTH(thumb)), 0) AS n FROM rcp_photos")["n"])}
