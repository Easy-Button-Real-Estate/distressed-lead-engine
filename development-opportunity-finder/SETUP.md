# Setup (about 10 minutes)

## Claude (easiest)

1. You need a paid Claude plan and **Claude Code** installed (claude.com/claude-code). You also need Python 3.10+ (python.org/downloads).
2. Unzip this folder somewhere (for example Documents/development-opportunity-finder).
3. Open a terminal in that folder and type `claude`.
4. Say: **"Set this up for <your city, state>"**. Claude looks up that city's zoning code, fills in `config/my-market.yaml`, cites the pages, and tells you what it could not confirm. It works for any US city or county.
5. Drop your PropStream or assessor CSV in the folder and say **"screen this list"**.
6. Open `output/opportunities.csv` in Google Sheets (File > Import > Upload) or Excel.

Want to see it work before you touch your own config? Say **"screen the sample list with the Seattle example"**.

The skill lives in `.claude/skills/development-opportunity-finder/`, so Claude picks it up when you open this folder. To use it from any folder, copy that folder into `~/.claude/skills/`.

## Just the command

```
pip install -r requirements.txt
python -m dof.run --csv your-export.csv --config config/my-market.yaml
```

Edit `config/my-market.yaml` first, or pass one of the example configs:

```
python -m dof.run --csv samples/sample_properties.csv --config config/examples/seattle-wa.yaml
python -m dof.run --csv samples/sample_properties.csv --config config/examples/portland-or.yaml
python -m dof.run --csv samples/sample_properties.csv --config config/examples/austin-tx.yaml
python -m dof.run --csv samples/sample_properties.csv --config config/examples/minneapolis-mn.yaml
```

The example configs are there to try the tool. Verify the numbers before you rely on them. The sources are at the bottom of each file.

## What to export from PropStream

Include whatever you have of: address, city, state, zip, APN, owner, property type, zoning, lot size, lot width, building sqft, beds, baths, stories, basement sqft, finished basement, basement type, garage, units, corner lot, alley. Missing columns are fine. The summary tells you which checks could not run.
