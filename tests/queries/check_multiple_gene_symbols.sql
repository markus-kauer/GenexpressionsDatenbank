SELECT gene_symbol,
  sample_id,
  COUNT(*) AS entry_count
FROM GenExpression
WHERE sample_id = 'GSM452660'
GROUP BY gene_symbol,
  sample_id
HAVING COUNT(*) > 1;