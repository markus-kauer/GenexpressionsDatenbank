SELECT ga.gene_symbol,
   mm.sample_id,
   COUNT(DISTINCT mm.id_ref) AS id_ref_count
FROM MicroarrayMeasurements mm
   JOIN GeneAnnotations ga ON mm.id_ref = ga.id
   AND mm.platform_id = ga.platform_id
WHERE mm.sample_id = 'GSM400174'
GROUP BY ga.gene_symbol,
   mm.sample_id
HAVING id_ref_count > 1;