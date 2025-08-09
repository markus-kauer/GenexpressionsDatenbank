SELECT gene_symbol,
  sample_id,
  value
FROM GenExpression
WHERE sample_id = 'GSM400174'
  AND gene_symbol IN ('AAK1', 'A1CF')
ORDER BY gene_symbol;