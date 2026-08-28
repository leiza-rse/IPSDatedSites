# sql/

**The PostgreSQL statements are not in this repository.**

`sql/*.sql` is gitignored. What is tracked here is `MANIFEST.json`: for
each statement its size, its SHA-256 and the revision it was at — enough
to tell whether two people hold the same file, and not enough to
reconstruct it.

## Why

The full query names the tables, columns and quality flags of a live
research database that also answers a public web application. Publishing
the schema hands nobody the keys, but it removes a step for anyone looking
for a way in, and it buys nothing: **the pipeline never reads
PostgreSQL.** `python py/main.py` takes its data from the public REST
endpoints, or from `data/` when offline.

## What is not lost

The datings stay reproducible without the SQL. `py/ips_model.py` is a
complete second implementation of the algorithm, it runs from the same
public endpoint anyone else can read, and every build compares it column
by column against the database's own aggregation of the same stamps.
Somebody who wants to check the datings needs the model and the data.
Both are here.

## How we know the repository and the CFM application are in step

Not by comparing text. By comparing results.

Step 0 of every build recomputes the datings with `py/ips_model.py` and
checks them against `datedsitesstatistics`, which is what the database
itself produces from the same statement the ColdFusion page runs. A
disagreement is fatal and stops the build:

    Every column agrees. The Python model reproduces the SQL.
    Cross-check       : agrees with the database on all 41 findspots

That is a stronger guarantee than a hash of the query would be. A text
comparison fires when somebody edits a comment and stays silent when a
rewrite happens to produce the same numbers; it measures the wrong thing.
The manifest answers a different and smaller question — *which file am I
holding* — and does not pretend to answer this one.

## Where the statements are

On the machines that maintain them, and in the database. Keep them at
`sql/` locally: `py/make_sql.py` reads `sql/IPSDatedSites.sql` and renders
the ColdFusion and psql forms from it, and `py/sql_manifest.py` looks for
them there.

After editing one:

    python py/sql_manifest.py --update

and commit `MANIFEST.json`, so that the next person can tell which
revision the repository was last built against.

## A note on the history

These files were tracked until August 2026, so they are still reachable
through the commit history of this repository even though they no longer
appear in the working tree. Removing them from `HEAD` stops them being
published going forward; it does not retract what was published. Rewriting
the history would, and at the time of writing this repository has no forks
and no watchers, which makes that unusually clean to do — but it
invalidates every existing clone, so it is a separate decision rather than
a side effect of this one.
