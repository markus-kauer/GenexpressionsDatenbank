import numpy as np
from collections import defaultdict

class GEOExportTest:
    def __init__(self):
        pass

    def quantile_normalize(self, values_matrix, log_transform=False):
        """
        """
        values_matrix = np.where(np.isnan(values_matrix) | ~np.isfinite(values_matrix), 0, values_matrix)

        sorted_idx = np.argsort(values_matrix, axis=0)  
        sorted_values = np.sort(values_matrix, axis=0)  
        
        print("\nSortiert:")
        print(sorted_values)

        rank_mean = np.nanmean(sorted_values, axis=1)

        normalized_values = np.zeros_like(values_matrix)

        for i in range(values_matrix.shape[1]):
            for j in range(values_matrix.shape[0]):
                normalized_values[sorted_idx[j, i], i] = rank_mean[j]

        return normalized_values

    def collect_data_for_export(self, selected_ids, normalization_method='quantile', log_transform=False):
        """
        """
        expression_rows = [
            (1, 101, 10.5, 'P', 0.01, 'GeneA', 1, 'Group1', 'G1', 'SeriesType1', 'BTO1', 'Tissue1'),
            (2, 101, 20.0, 'P', 0.02, 'GeneB', 1, 'Group1', 'G1', 'SeriesType1', 'BTO1', 'Tissue1'),
            (4, 101, 12.0, 'P', 0.01, 'GeneA', 1, 'Group1', 'G1', 'SeriesType1', 'BTO1', 'Tissue1'),  
            (2, 102, 25.0, 'P', 0.02, 'GeneB', 1, 'Group2', 'G2', 'SeriesType2', 'BTO2', 'Tissue2'),
            (1, 103, 15.0, 'P', 0.01, 'GeneA', 2, 'Group3', 'G3', 'SeriesType3', 'BTO3', 'Tissue3'),
            (2, 103, 22.0, 'P', 0.02, 'GeneB', 2, 'Group3', 'G3', 'SeriesType3', 'BTO3', 'Tissue3'),
            (3, 103, 18.0, 'P', 0.01, 'GeneC', 2, 'Group3', 'G3', 'SeriesType3', 'BTO3', 'Tissue3')   
        ]

        samples = defaultdict(lambda: defaultdict(list)) 
        sample_to_series = {}  
        gene_symbol_order = []  
        additional_data = {}  

        for row in expression_rows:
            sample_id = row[1]
            gene_symbol = row[5]
            value = row[2]

            samples[sample_id][gene_symbol].append(value)

            if gene_symbol not in gene_symbol_order:
                gene_symbol_order.append(gene_symbol)
            
            sample_to_series[sample_id] = row[6]
            
            additional_data[sample_id] = {
                'sample_group_name': row[7],
                'sample_group_short_name': row[8],
                'series_type': row[9],
                'bto_id': row[10],
                'tissue_type': row[11]
            }

        print("\nAppendierte Daten:")
        for sample_id, gene_values in samples.items():
            print(f"Sample ID {sample_id}:")
            for gene, values in gene_values.items():
                print(f"  {gene}: {values}")
        
        averaged_samples = defaultdict(dict)
        for sample_id, gene_values in samples.items():
            for gene_symbol, values in gene_values.items():
                clean_values = np.array([v for v in values])
                averaged_samples[sample_id][gene_symbol] = np.mean(clean_values)

        print("\nGemittelte Samples:")
        for sample_id, gene_values in averaged_samples.items():
            print(f"Sample ID {sample_id}:")
            for gene, value in gene_values.items():
                print(f"  {gene}: {value:.2f}")
        
        normalized_samples = defaultdict(dict)
        if normalization_method == 'quantile':
            gene_symbols = gene_symbol_order  
            sample_ids = list(averaged_samples.keys())

            values_matrix = np.full((len(gene_symbols), len(sample_ids)), 0.0)
            for j, sample_id in enumerate(sample_ids):
                for i, gene_symbol in enumerate(gene_symbols):
                    if gene_symbol in averaged_samples[sample_id]:
                        values_matrix[i, j] = averaged_samples[sample_id][gene_symbol]
            
            print("\ngene_symbols:", gene_symbols)
            print("\nMatrix der Werte (vor der Normalisierung):")
            print(values_matrix)

            normalized_matrix = self.quantile_normalize(values_matrix, log_transform)

            for j, sample_id in enumerate(sample_ids):
                for i, gene_symbol in enumerate(gene_symbols):
                    normalized_samples[sample_id][gene_symbol] = normalized_matrix[i, j]
                    
            print("\nMatrix der Werte (nach der Normalisierung):")
            print(normalized_matrix)

        return normalized_samples, sample_to_series, additional_data


geo_export_test = GEOExportTest()
selected_ids = [101, 102, 103]
normalized_samples, sample_to_series, additional_data = geo_export_test.collect_data_for_export(selected_ids)
