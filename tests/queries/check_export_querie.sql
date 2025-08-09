SELECT ge.gene_symbol,
  ge.sample_id,
  ge.value,
  ss.series_id,
  sg.name AS sample_group_name,
  sg.short_name AS sample_group_short_name,
  series.type AS series_type,
  series.bto_id,
  t.name AS tissue_type
FROM GenExpression ge
  JOIN Sample s ON ge.sample_id = s.id
  JOIN SampleSeries ss ON s.id = ss.sample_id
  JOIN Series series ON ss.series_id = series.id
  JOIN sample_group_assignments sga ON s.id = sga.sample_id
  JOIN sample_groups sg ON sga.group_id = sg.id
  JOIN tissue_types t ON s.tissue_type_id = t.id
WHERE ge.sample_id = 'GSM400174'
  AND ge.gene_symbol IN ('AAK1', 'A1CF');