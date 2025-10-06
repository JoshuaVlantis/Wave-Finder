# Wave Finder is now Open Source

Today I’m opening up the Wave Finder codebase. The tools, maps, and ideas that started as a local project are now available for anyone to run, explore, and improve.

## What’s included

- Static website (Leaflet map, wind overlay, MPA data, limits, blog, records)
- Minimal Node.js API (Express + MariaDB) for spots and records
- Python tools to train and predict underwater visibility

Everything lives in a single repo:

- GitHub: https://github.com/JoshuaVlantis/Wave-Finder
- Website: https://wavefinder.org

## Run it locally (no code changes needed)

You can host the website locally with Coolify and still use the production API. The README has a step-by-step guide:

- README (Local hosting with Coolify): https://github.com/JoshuaVlantis/Wave-Finder#local-hosting-with-coolify

If you prefer Docker Compose from Git, there’s an example in the `deploy/` folder.

## Contribute

If you’d like to help, here are a few easy ways to get started:

- Fork the repo and run the site locally
- Fix a typo or improve docs (PRs welcome!)
- Open an issue with a bug report or small feature idea
- Share dive/vis reports to help train the model

## Why open source?

Wave Finder is community-driven. Opening the code helps the project grow faster and stay transparent. It also makes it easier for local divers to tweak things for their coastline, or for developers to build tools on top of the data.

## What’s next

- More spots and better regional notes
- Visibility model improvements as we gather more data
- Cleaner API and deployment options

If you’ve read this far: thank you. Your feedback and contributions make this better.

— Joshua

> In open source, your work belongs to no one and everyone at the same time. That is the true power of freedom.
