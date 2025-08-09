WITH microarray_genes AS (
    SELECT DISTINCT ga.gene_symbol,
        mm.sample_id
    FROM MicroarrayMeasurements mm
        JOIN GeneAnnotations ga ON mm.id_ref = ga.id
        AND mm.platform_id = ga.platform_id
    WHERE mm.sample_id IN ('GSM400176', 'GSM400174', 'GSM400175')
),
genexpression_genes AS (
    SELECT DISTINCT ge.gene_symbol,
        ge.sample_id
    FROM GenExpression ge
    WHERE ge.sample_id IN ('GSM400176', 'GSM400174', 'GSM400175')
)
SELECT ge.gene_symbol,
    ge.sample_id
FROM genexpression_genes ge
    LEFT JOIN microarray_genes mg ON ge.gene_symbol = mg.gene_symbol
    AND ge.sample_id = mg.sample_id
WHERE mg.gene_symbol IS NULL;