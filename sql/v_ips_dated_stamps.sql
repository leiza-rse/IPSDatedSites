-- ==========================================================================
-- v_ips_dated_stamps — one row per dated stamp
-- ==========================================================================
--
-- WHY THIS VIEW EXISTS
-- --------------------
-- sql/IPSDatedSites.sql delivers a finished result: one row per findspot,
-- every quantity already aggregated. That is what the figure needs, but it
-- means the model lives in the database and nowhere else — it cannot be
-- read, tested or reproduced without a PostgreSQL instance.
--
-- This view delivers the INPUT instead: the stamps that survive the data
-- filters, with the potter dates attached and nothing computed. Feed it to
-- py/ips_model.py and the same numbers come out, so the algorithm exists
-- twice and the two can be compared. Publish it over REST and anybody can
-- recompute the datings without database access at all.
--
-- WHAT IS FILTERED HERE, AND WHAT IS NOT
-- --------------------------------------
-- Filtered here, because these are statements about DATA QUALITY and belong
-- with the data:
--
--   isdate / sitecharacter / findspot   the selection of dated findspots
--   the eleven placeholder pairs        potters whose dating is not usable
--
-- NOT filtered here, because these are EDITORIAL decisions that change more
-- often than the data and belong to whoever draws the figure:
--
--   the Bregenz exclusion               under review, will return
--   any minimum number of stamps        a display threshold
--
-- py/ips_model.py takes both as parameters. Keeping them out of the view
-- means a change of mind about Bregenz does not require a database
-- migration.
--
-- ON THE JOIN
-- -----------
-- The main query uses LEFT JOIN tblpotter and then excludes the placeholder
-- pairs. A stamp whose potter is not in tblpotter yields NULL for the pair
-- comparison, and NULL is not TRUE, so the row is dropped anyway. An INNER
-- JOIN says the same thing and says it visibly.
--
-- Expect roughly 1 400 rows for the current corpus — small enough to serve
-- as JSON over REST without paging.
-- ==========================================================================

CREATE OR REPLACE VIEW v_ips_dated_stamps AS
SELECT
    vds.id              AS the_id,
    di.site             AS the_site,
    di.findspot         AS the_findspot,
    di.siteancientname  AS latinsitename,
    di.coordinate1      AS long,
    di.coordinate2      AS lat,
    di.pleiades,

    -- The stamp itself. `number` is what COUNT(di.number) counts in the
    -- aggregate query, so it has to travel: a NULL there is one stamp
    -- fewer, and the reimplementation has to see the same NULLs.
    di.number           AS stamp_number,
    di.pottername,

    -- NULL where no die is recorded. The k factor is built only from the
    -- rows where this is set, which is why n_stamps_die is smaller than
    -- count_stamps and why both are exported.
    di.die,

    p.datemin,
    p.datemax

FROM tbldistribution AS di
JOIN tblpotter AS p
  ON lower(trim(di.pottername)) = lower(trim(p.pottername))
LEFT JOIN v_discoverysite AS vds
  ON di.site = vds.label

WHERE di.isdate        = U&'\0398'      -- greek capital theta
  AND di.sitecharacter = U&'\03A3'      -- greek capital sigma
  AND di.findspot IS NOT NULL

  -- The eleven placeholder combinations. A pair, not two independent
  -- values: a potter running 90 to 120 is perfectly good evidence, and an
  -- earlier version of this filter threw exactly those away.
  AND (p.datemin, p.datemax) NOT IN (
        (-30, 150), (0, 100), (0, 120), (0, 130), (0, 150),
        (0, 180), (0, 270), (100, 200), (150, 270),
        (160, 260), (165, 270)
      );

COMMENT ON VIEW v_ips_dated_stamps IS
  'One row per dated samian stamp with its potter dates attached. Input to '
  'py/ips_model.py, which recomputes the findspot datings from it. Data '
  'filters are applied here; editorial exclusions (Bregenz, minimum stamp '
  'count) are parameters of the script, not of the view.';


-- --------------------------------------------------------------------------
-- The export the script expects
-- --------------------------------------------------------------------------
-- Column order does not matter, names do. Sorted so that two exports of an
-- unchanged database are byte-identical and a diff means something.
--
--   \copy (SELECT * FROM v_ips_dated_stamps
--          ORDER BY the_site, the_findspot, pottername, die, stamp_number)
--     TO 'ips_stamps.csv' WITH (FORMAT csv, HEADER true)
--
-- Over REST, the same ordering, so a cached copy can be compared with a
-- fresh one without normalising first.
