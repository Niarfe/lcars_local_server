# External Content Roots

LCARS v25 supports keeping user content outside the app folder.

Edit `content_config.json` next to `app.py`:

```json
{
  "markdown_dir": "/Users/praedator/Documents/LCARS_CONTENT/markdown",
  "books_dir": "/Users/praedator/Documents/LCARS_CONTENT/books",
  "sounds_dir": "/Users/praedator/Documents/LCARS_CONTENT/sounds"
}
```

Then restart LCARS.

Suggested setup:

```bash
mkdir -p ~/Documents/LCARS_CONTENT/markdown
mkdir -p ~/Documents/LCARS_CONTENT/books
mkdir -p ~/Documents/LCARS_CONTENT/sounds

cp -R markdown/* ~/Documents/LCARS_CONTENT/markdown/
cp -R books/* ~/Documents/LCARS_CONTENT/books/

cd ~/Documents/LCARS_CONTENT
git init
git add .
git commit -m "Initial LCARS content backup"
```

If a configured folder does not exist, LCARS creates it. Your old local `markdown/` and `books/` folders are not deleted.
