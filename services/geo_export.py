import io
import traceback
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime
import json

class GEOExport:
    def __init__(self, db_manager):
        self.db_manager = db_manager

    async def ensure_connected(self):
        await self.db_manager.ensure_connected()

    async def record_export(self, user_id, sample_list, normalization_method, scaling_method):
        """
        Protokolliert den Export einer Genexpressionsmatrix in der Datenbank.
        """
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            if user_id:
                await cursor.execute(
                    "INSERT INTO ExportHistory (user_id, sample_list, normalization_method, scaling_method, export_date) VALUES (%s, %s, %s, %s, %s)",
                    (user_id, ','.join(sample_list), normalization_method, scaling_method, datetime.utcnow())
                )
            else:
                await cursor.execute(
                    "INSERT INTO ExportHistory (sample_list, normalization_method, scaling_method, export_date) VALUES (%s, %s, %s, %s)",
                    (','.join(sample_list), normalization_method, scaling_method, datetime.utcnow())
                )
            await conn.commit()
        except Exception as e:
            print(f"Error recording export: {e}")
            traceback.print_exc()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def collect_data_for_selection(self):
        """
        Fetch hierarchical mapping for combo tree:
        - Disease: `disease`
        - Sub-Type: `subtype`
        - Tissue: `tissue_types.name`
        - Series: `series_id`
        - Sample: `sample_id`
        """
        query = """
        SELECT s.id AS series_id, s.title AS series_title, s.type AS series_type,
            p.id AS platform_id, p.title AS platform_title,
            g.id AS sample_id, g.title AS sample_title, g.type AS sample_type,
            sg.id AS group_id, sg.disease, sg.subtype,
            t.name AS sample_tissue_type
        FROM Series s
        JOIN Platform p ON s.platform_id = p.id
        JOIN SampleSeries ss ON ss.series_id = s.id
        JOIN Sample g ON g.id = ss.sample_id
        JOIN sample_group_assignments sga ON g.id = sga.sample_id
        JOIN sample_groups sg ON sga.group_id = sg.id
        JOIN tissue_types t ON g.tissue_type_id = t.id
        WHERE s.is_finished = TRUE
        """

        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query)
            rows = await cursor.fetchall()
        except Exception as e:
            print(f"Database error in collect_data_for_selection: {e}")
            return []
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

        # Map data to tree structure
        data = [
            {
                'group_id': row[8], 
                'disease': row[9], # Disease
                'sub_type': row[10],  # Subtype
                'series_id': row[0],  # Series
                'series_type': row[2], 
                'sample_id': row[5],  # Sample
                'sample_type': row[7],
                'sample_tissue_type': row[11]  # Tissue
            }
            for row in rows
        ]


        # Create the formatted data for the combo tree
        formatted_data = self.generate_combo_tree(data)
        return formatted_data

    def generate_combo_tree(self, data):
        """
        Generate hierarchical structure for different views of combo tree.
        """
        # Hierarchical groupings
        by_disease = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        by_subtype = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        by_tissue = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

        # Organize data into hierarchical groups
        for row in data:
            disease = row['disease']
            subtype = row['sub_type']
            tissue = row['sample_tissue_type']
            series = row['series_id']
            sample = row['sample_id']

            # Group by disease -> subtype -> tissue
            by_disease[disease][subtype][tissue].append({'series': series, 'sample': sample})

            # Group by subtype -> tissue -> disease
            by_subtype[subtype][tissue][disease].append({'series': series, 'sample': sample})

            # Group by tissue -> disease -> subtype
            by_tissue[tissue][disease][subtype].append({'series': series, 'sample': sample})

        return [
            {
                "id": "disease",
                "title": "Disease",
                "subs": self.build_hierarchy(by_disease, 'subtype', 'tissue', 'series', 'sample')
            },
            {
                "id": "subtype",
                "title": "Subtype",
                "subs": self.build_hierarchy(by_subtype, 'tissue', 'disease', 'series', 'sample')
            },
            {
                "id": "tissue",
                "title": "Tissue",
                "subs": self.build_hierarchy(by_tissue, 'disease', 'subtype', 'series', 'sample')
            }
        ]

    def build_hierarchy(self, hierarchy, level_2, level_3, series_key, sample_key):
        """
        Recursively build nested structure for the combo tree.
        """
        result = []
        level_1 = 'disease' if level_2 == 'subtype' else 'subtype' if level_2 == 'tissue' else 'tissue'
        
        for level_1_key, level_2_dict in hierarchy.items():
            level_2_children = []
            for level_2_key, level_3_dict in level_2_dict.items():
                level_3_children = []
                for level_3_key, items in level_3_dict.items():
                    
                    series_children = [
                        {
                            "id": f"{level_1_key}|{level_2_key}|{level_3_key}|{item['series']}|{item['sample']}",  
                            "title": f"{item['sample']} [sample]",
                        }
                        for item in items
                    ]
                    level_3_children.append({
                        "id": f"{level_1_key}|{level_2_key}|{level_3_key}",
                        "title": f"{level_3_key} [{level_3}]",
                        "subs": series_children
                    })

                level_2_children.append({
                    "id": f"{level_1_key}|{level_2_key}",
                    "title": f"{level_2_key} [{level_2}]",
                    "subs": level_3_children
                })

            result.append({
                "id": level_1_key,
                "title": f"{level_1_key} [{level_1}]",
                "subs": level_2_children
            })
        return result

    def quantile_normalize(self, values_matrix):
        """
        """

        # NaN oder nicht-numerische Werte in 0 umwandeln
        values_matrix = np.where(np.isnan(values_matrix) | ~np.isfinite(values_matrix), 0, values_matrix)
        
        # Sortiere die Werte jeder Probe (Spalte)
        sorted_idx = np.argsort(values_matrix, axis=0)
        sorted_values = np.sort(values_matrix, axis=0)

        # Berechne den Mittelwert für jeden Rang über alle Proben hinweg
        rank_mean = np.mean(sorted_values, axis=1)
        
        # Nach der Berechnung des Rangmittelwerts
        if np.any(rank_mean < 0):
            print("Negative values detected in rank means during quantile normalization:")
            print(rank_mean)

        # Erstelle ein neues Array, um die normalisierten Werte zu speichern
        normalized_values = np.zeros_like(values_matrix)
        
        # Nach der Normalisierung
        if np.any(normalized_values < 0):
            print("Negative values detected in normalized values during quantile normalization:")
            print(normalized_values)

        # Weise die Rang-Mittelwerte den normalisierten Werten zu
        for i in range(values_matrix.shape[1]):
            normalized_values[sorted_idx[:, i], i] = rank_mean

        return normalized_values
    
    def minmax_normalize(self, values):
        """
        Min-Max-Normalisierung: Der kleinste Wert wird auf 0, der größte Wert auf 1 skaliert.
        Liefert auch die Min- und Maxwerte zurück, um sie in die Metadaten aufzunehmen.
        """

        if len(values) == 0:  
            return np.nan, np.nan, np.nan  # Rückgabe von NaN bei leeren Werten

        min_val = np.nanmin(values)  
        max_val = np.nanmax(values)

        if max_val == min_val:  # Vermeide Division durch 0
            return np.zeros_like(values), min_val, max_val

        return (values - min_val) / (max_val - min_val), min_val, max_val


    def zscore_normalize(self, values):
        """
        Z-Score-Normalisierung standardisiert die Daten, indem sie den Mittelwert subtrahiert und durch die Standardabweichung teilt.
        Fügt auch Mittelwert und Standardabweichung hinzu, um diese in die Metadaten aufzunehmen.
        """
        values = np.array(values)

        if len(values) == 0:
            return np.full_like(values, np.nan), np.nan, np.nan  

        mean = np.nanmean(values)
        std = np.nanstd(values)

        if std == 0:
            return np.zeros_like(values), mean, std  # Vermeide Division durch Null

        normalized_values = (values - mean) / std

        return normalized_values, mean, std

    async def collect_data_for_export(self, selected_ids, normalization_method='quantile', log_transform=False):
        """
        Collects data for export and normalizes it based on the method.
        """
        expression_query = """
        SELECT ge.gene_symbol, ge.sample_id, ge.value, 
            ss.series_id, sg.disease,
            sg.subtype,  
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
        WHERE ge.sample_id IN (%s)
        """ % ','.join(['%s'] * len(selected_ids))


        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(expression_query, selected_ids)
            expression_rows = await cursor.fetchall()
        except Exception as e:
            print(f"Error collecting data for export: {e}")
            return None, None, None, selected_ids
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

        # Organize data by class label
        samples_by_class = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        sample_to_series = {}
        gene_symbol_order = []
        additional_data = {}
        samples = defaultdict(dict) 
        # samples = defaultdict(lambda: defaultdict(list))
        
        # duplicates
        duplicates = defaultdict(lambda: defaultdict(list))

        # Collect values by sample_id and gene_symbol, grouped by class
        for row in expression_rows:
            gene_symbol = row[0]
            sample_id = row[1]
            value = float(row[2])
            series_id = row[3]
            disease = row[4]  
            
            # Log-transform the value if needed
            if log_transform:
                value = np.log1p(value)
                
            if np.isnan(value) or not np.isfinite(value):
                print(f"Invalid value for {gene_symbol} in sample {sample_id}: {value}")
                
            if normalization_method == 'quantile':
                samples_by_class[disease][sample_id][gene_symbol] = value
            else:
                if gene_symbol in samples[sample_id]:
                    duplicates[sample_id][gene_symbol].append(value)
                    
                samples[sample_id][gene_symbol] = value
                # samples[sample_id][gene_symbol].append(value)
                
            if gene_symbol not in gene_symbol_order:
                gene_symbol_order.append(gene_symbol)
            
            if sample_id not in sample_to_series:
                sample_to_series[sample_id] = series_id

            additional_data[sample_id] = {
                'disease': row[4],
                'subtype': row[5],
                'series_type': row[6],
                'bto_id': row[7],
                'tissue_type': row[8]  
            }
        
        normalized_samples = defaultdict(dict)
        normalization_metadata = defaultdict(dict)
                
        if duplicates: 
            print("WARNING")
            for sample_id, gene_symbols in duplicates.items():
                for gene_symbol, values in gene_symbols.items():
                    # Only print the warning if there are more than one value for any gene symbol
                    if len(values) > 1:
                        print(f"Warning: Duplicate gene symbol {gene_symbol} for sample {sample_id} with values {values}")
                        

            
        if len(gene_symbol_order) > len(set(gene_symbol_order)):
            print("Warning: Duplicate gene symbols found in gene_symbol_order")
            
        if normalization_method == 'quantile':
            for class_label, samples in samples_by_class.items():
                sample_ids = list(samples.keys())
                
                values_matrix = np.array([
                    [samples[sample_id].get(gene_symbol, 0.0) for sample_id in sample_ids]
                    for gene_symbol in gene_symbol_order
                ])

                normalized_matrix = self.quantile_normalize(values_matrix)
                
                

                # Map normalized data back to samples
                for j, sample_id in enumerate(sample_ids):
                    for i, gene_symbol in enumerate(gene_symbol_order):
                        normalized_samples[sample_id][gene_symbol] = normalized_matrix[i, j]
                    
                    # Calculate normalization metadata
                    sample_values = normalized_matrix[:, j]
                    normalization_metadata[sample_id] = {
                        'mean': np.mean(sample_values),
                        'std': np.std(sample_values),
                        'min': np.min(sample_values),
                        'max': np.max(sample_values)
                    }
                    
        else:
            sample_ids = list(samples.keys())
            
            for sample_id in sample_ids:
                values_array = np.array([samples[sample_id].get(gene_symbol, np.nan) for gene_symbol in gene_symbol_order])
                mean, std, min_val, max_val = None, None, None, None
                
                if normalization_method == 'zscore':
                    normalized_values, mean, std = self.zscore_normalize(values_array)
                    normalization_metadata[sample_id] = {'mean': mean, 'std': std}
                elif normalization_method == 'minmax':
                    normalized_values, min_val, max_val = self.minmax_normalize(values_array)
                    normalization_metadata[sample_id] = {'min': min_val, 'max': max_val}
                else:
                    normalized_values = values_array
                    
                for i, gene_symbol in enumerate(gene_symbol_order):
                    normalized_samples[sample_id][gene_symbol] = normalized_values[i]
                    
                # Calculate normalization metadata
                if mean is None:
                    mean = np.nanmean(normalized_values)
                if std is None:
                    std = np.nanstd(normalized_values)
                if min_val is None:
                    min_val = np.nanmin(normalized_values)
                if max_val is None:
                    max_val = np.nanmax(normalized_values)
                        
                normalization_metadata[sample_id].update({'mean': mean, 'std': std, 'min': min_val, 'max': max_val})
                print(normalization_metadata[sample_id])

        missing_samples = list(set(selected_ids) - set(samples.keys()))

        return normalized_samples, sample_to_series, gene_symbol_order, additional_data, normalization_metadata, missing_samples


    async def create_csv_buffers(self, normalized_samples, sample_to_series, gene_symbol_order, additional_data, normalization_method, log_transform, normalization_metadata):
        """
        Erstellt CSV-Puffer für den Export der normalisierten Daten.
        """
        # Verwende gene_symbol_order, da es die Reihenfolge der Gene ist
        gene_symbols = gene_symbol_order  
        gene_expression_data = {'gene_symbol': gene_symbols}

        max_length = max((len(normalized_samples[sample_id]) for sample_id in normalized_samples.keys()), default=0.0)
        for sample_id in normalized_samples.keys():
            gene_expression_data[sample_id] = [
                normalized_samples[sample_id].get(gene_symbol, 0.0) for gene_symbol in gene_symbols
            ]
            while len(gene_expression_data[sample_id]) < max_length:
                gene_expression_data[sample_id].append(0.0)

        # Create gene expression DataFrame
        gene_expression_df = pd.DataFrame(gene_expression_data)

        # Export Gene Expression Matrix to in-memory buffer
        gene_expression_buffer = io.BytesIO()
        gene_expression_df.to_csv(gene_expression_buffer, index=False)
        gene_expression_buffer.seek(0)

        # Prepare metadata data for each sample
        metadata_data = []
        metadata_columns = ['Sample', 'Series', 'Disease', 'Tissue Type', 
                            'Series Type', 'BTO ID', 'Series Tissue Type', 'Normalization Method', 
                            'Log Transformation', 'Mean', 'Standard Deviation', 'Min Value', 'Max Value']
        
        for sample_id, series_id in sample_to_series.items():
            additional_info = additional_data.get(sample_id, {})
            
            mean = normalization_metadata[sample_id].get('mean', 0.0)
            std = normalization_metadata[sample_id].get('std', 0.0)
            min_val = normalization_metadata[sample_id].get('min', 0.0)
            max_val = normalization_metadata[sample_id].get('max', 0.0)
        
            meta_entry = [
                sample_id,
                series_id,
                additional_info.get('disease', ''),
                additional_info.get('tissue_type', ''),
                additional_info.get('series_type', ''),
                additional_info.get('bto_id', ''),
                additional_info.get('sub_type', ''),
                normalization_method,
                "log1" if log_transform else "",
                mean,
                std, 
                min_val, 
                max_val  
            ]

            metadata_data.append(meta_entry)

        # Create metadata DataFrame
        metadata_df = pd.DataFrame(metadata_data, columns=metadata_columns)

        # Export metadata to in-memory buffer
        metadata_buffer = io.BytesIO()
        metadata_df.to_csv(metadata_buffer, index=False)
        metadata_buffer.seek(0)

        return gene_expression_buffer, metadata_buffer

    async def export_csv(self, selected_ids, normalization_method='quantile', log_transform=False, api_call=False):
        """
        Exportiert die Daten als CSV-Dateien und bereitet sie für den Download vor.
        """
        try:
            normalized_samples, sample_to_series, gene_symbol_order, additional_data, normalization_metadata, missing_samples = await self.collect_data_for_export(
                selected_ids, normalization_method, log_transform
            )
            
            if normalized_samples is None:
                raise ValueError("Data collection failed.")

            gene_expression_buffer, metadata_buffer = await self.create_csv_buffers(
                normalized_samples, 
                sample_to_series, 
                gene_symbol_order, 
                additional_data, 
                normalization_method, 
                log_transform, 
                normalization_metadata
            )

            # Handle API call differently if needed
            if api_call:
                gene_expression_csv_data = gene_expression_buffer.getvalue().decode('utf-8')
                metadata_csv_data = metadata_buffer.getvalue().decode('utf-8')
                return gene_expression_csv_data, metadata_csv_data, missing_samples
            else:
                # Return buffers for non-API calls
                return gene_expression_buffer, metadata_buffer

        except Exception as e:
            error_message = f"Error in exporting gene expressions: {e}"
            print(error_message)
            traceback.print_exc()

            if api_call:
                return {
                    "status": "error",
                    "message": error_message,
                    "traceback": traceback.format_exc()
                }, None, None
            else:
                return None, None, None

    async def generate_boxplot(self, selected_ids, normalization_method='quantile', log_transform=False):
        """
        Generates data for a boxplot based on the selected samples.
        """
        try:
            conn = await self.db_manager.get_read_connection()
            cursor = await conn.cursor()
            try:
                query = """
                    SELECT ge.sample_id, ge.value, ge.gene_symbol, sg.disease
                    FROM GenExpression ge
                    JOIN sample_group_assignments sga ON ge.sample_id = sga.sample_id
                    JOIN sample_groups sg ON sga.group_id = sg.id
                    WHERE ge.sample_id IN (%s)
                """ % ','.join(['%s'] * len(selected_ids))
                await cursor.execute(query, selected_ids)
                data = await cursor.fetchall()

                samples_by_class = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
                gene_symbol_order = []
                # samples = defaultdict(lambda: defaultdict(list))
                samples = defaultdict(dict)

                # Collect and organize samples and genes
                for row in data:
                    sample_id, value, gene_symbol, disease = row
                    value = float(value)

                    if log_transform:
                        value = np.log1p(value)
                        
                    if normalization_method == 'quantile':
                        samples_by_class[disease][sample_id][gene_symbol] = value
                    else:
                        samples[sample_id][gene_symbol] = value
                        # samples[sample_id][gene_symbol].append(value)
                        if gene_symbol in samples[sample_id]:
                            print(f"Warning: Duplicate gene symbol {gene_symbol} for sample {sample_id}")

                    if gene_symbol not in gene_symbol_order:
                        gene_symbol_order.append(gene_symbol)

                normalized_samples = defaultdict(dict)
                
                if normalization_method == 'quantile':
                    for class_label, samples in samples_by_class.items():
                        sample_ids = list(samples.keys())
                        
                        values_matrix = np.array([
                            [samples[sample_id].get(gene_symbol, 0.0) for sample_id in sample_ids]
                            for gene_symbol in gene_symbol_order
                        ])

                        normalized_matrix = self.quantile_normalize(values_matrix)

                        for j, sample_id in enumerate(sample_ids):
                            for i, gene_symbol in enumerate(gene_symbol_order):
                                normalized_samples[sample_id][gene_symbol] = normalized_matrix[i, j]

                else:
                    
                    sample_ids = list(samples.keys())
                    
                    for sample_id in sample_ids:
                        values_array = np.array([samples[sample_id].get(gene_symbol, np.nan) for gene_symbol in gene_symbol_order])

                        if normalization_method == 'zscore':
                            normalized_values, mean, std = self.zscore_normalize(values_array)
                        elif normalization_method == 'minmax':
                            normalized_values, min_val, max_val = self.minmax_normalize(values_array)
                        else:
                            normalized_values = values_array
                            
                        for i, gene_symbol in enumerate(gene_symbol_order):
                            normalized_samples[sample_id][gene_symbol] = normalized_values[i]

                json_ready_samples = {
                    sample_id: [normalized_samples[sample_id].get(gene_symbol, 0.0) for gene_symbol in gene_symbol_order]
                    for sample_id in sample_ids
                }

                json_data = {"samples": json_ready_samples}
                json_string = json.dumps(json_data)

                # Validate JSON
                try:
                    json.loads(json_string)
                except json.JSONDecodeError as e:
                    print("Error validating JSON data:", e)
                    raise

                return json_data
            finally:
                await cursor.close()
                await self.db_manager.release_connection(conn)
        except Exception as e:
            print(f"Error generating boxplot: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            return {"error": str(e)}












