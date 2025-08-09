import re
import aiomysql
from quart import render_template, jsonify, redirect, url_for, g, send_file
from services.geo_data_import import GEODataImport
from services.geo_data_service import GEODataService
from services.gse_scanner import GSEScanner
from services.geo_export import GEOExport
from services.database_connection_manager import DatabaseConnectionManager
import uuid
from SPARQLWrapper import SPARQLWrapper, JSON
import asyncio

class GeoController:
    # Status codes: 400 = Bad Request, 500 = Internal Server Error
    def __init__(self):
        self.db_manager = DatabaseConnectionManager()
        self.loader = GEODataImport(self.db_manager)
        self.scanner = GSEScanner(self.db_manager)
        self.data_service = GEODataService(self.db_manager)
        self.geo_export = GEOExport(self.db_manager)

    async def create_tables(self):
        await self.db_manager.create_tables()

    async def ensure_connection(self):
        await self.db_manager.ensure_connected()

    async def information_page(self):
        return await render_template('information.html')
    
    async def update_series_status(self, gse_id, is_finished):
        await self.data_service.update_series_status(gse_id, is_finished)

    async def fetch_bto_details(self, bto_id):
        sparql_endpoint = "https://sparql.hegroup.org/sparql"
        query = f"""
        SELECT * FROM <http://purl.obolibrary.org/obo/merged/BTO> WHERE {{
            <http://purl.obolibrary.org/obo/{bto_id}> <http://www.w3.org/2000/01/rdf-schema#label> ?o .
        }}
        """
        print(f"Executing SPARQL query: {query}")

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.perform_request, sparql_endpoint, query)
        print(f"Received response: {response}")
        return response

    def perform_request(self, sparql_endpoint, query):
        sparql = SPARQLWrapper(sparql_endpoint)
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)
        try:
            response = sparql.query().convert()
            print(f"SPARQL response: {response}")
            tissue_type = self.extract_tissue_type(response)
            return {'tissue_type': tissue_type}
        except Exception as e:
            print(f"Error: {e}")
            return {'error': str(e)}, 500

    def extract_tissue_type(self, response):
        bindings = response.get('results', {}).get('bindings', [])
        if bindings:
            print(f"Found tissue type: {bindings[0]['o']['value']}")
            return bindings[0]['o']['value']
        return None

    async def export_page(self):
        tree_data = await self.geo_export.collect_data_for_selection()
        
        tree_data_valid = tree_data and any(node.get('subs') for node in tree_data)
        
        return await render_template('export.html', tree_data=tree_data, tree_data_valid=tree_data_valid)


    async def information(self):
        return await render_template('information.html')

    async def export_csv(self, request):
        try:
            if request.method == 'POST':
                # POST: Get data from JSON body
                data = await request.get_json()
                sample_list = data.get('sample_list', '').split(',')
                normalization_method = data.get('normalizationMethod', 'quantile')  # Get from JSON body
                log_transform = data.get('logTransform', False)  # Get logTransform from JSON body
            else:  # GET request
                # GET: Get data from URL parameters
                sample_list = request.args.get('sample_list', '').split(',')
                normalization_method = request.args.get('normalization_method', 'quantile')  # Get from URL params
                log_transform = request.args.get('log_transform', 'False').lower() == 'true'  # Handle boolean string

            print(f"Selected items: {sample_list}")
            print(f"Normalization method: {normalization_method}")
            print(f"Log transform: {log_transform}")

            # Export-Logik wie bisher
            gene_expression_buffer, metadata_buffer = await self.geo_export.export_csv(
                sample_list, normalization_method, log_transform, api_call=False
            )

            if gene_expression_buffer and metadata_buffer:
                user_id = g.user['id'] if g.user and 'id' in g.user else None

                await self.record_export(
                    user_id,
                    sample_list,
                    normalization_method,
                    log_transform
                )

                from zipfile import ZipFile
                from io import BytesIO

                zip_buffer = BytesIO()
                with ZipFile(zip_buffer, 'w') as zip_file:
                    zip_file.writestr('gene_expression_data.csv', gene_expression_buffer.getvalue())
                    zip_file.writestr('metadata.csv', metadata_buffer.getvalue())
                zip_buffer.seek(0)

                return await send_file(zip_buffer, as_attachment=True, attachment_filename='gene_expression_data.zip', mimetype='application/zip')
            else:
                print("Error: CSV buffers are None")
                return jsonify({'error': 'An error occurred while exporting data to CSV.'}), 500
        except Exception as e:
            print(f"Error in export_csv: {e}")
            return jsonify({'error': 'An error occurred while exporting data to CSV.'}), 500


    async def record_export(self, user_id, sample_list, normalization_method, scaling_method):
        await self.geo_export.record_export(user_id, sample_list, normalization_method, scaling_method)
        
    async def generate_boxplot(self, request):
        try:
            data = await request.get_json()
            selected_ids = data.get('sample_list', '')
            normalization_method = data.get('normalizationMethod', 'quantile')
            log_transform = data.get('logTransform', False)
            print("Selected items: ", selected_ids)

            # Call the function that generates the boxplot data
            result = await self.geo_export.generate_boxplot(selected_ids, normalization_method, log_transform)
            
            if 'error' in result:
                return jsonify({'error': result['error']}), 500
            
            # Debugging information from the result
            print(f"Length of returned samples: {len(result['samples'])}")
            print(f"Sample keys: {list(result['samples'].keys())}") 
            return jsonify(result)  
        except Exception as e:
            print(f"Exception in generate_boxplot: {str(e)}")
            return jsonify({'error': str(e)}), 500

    def validate_parameters(self, parameters):
        for value, validation_type in parameters:
            if validation_type in ['gse_id', 'gpl_id', 'gsm_id']:
                if not re.match(r"^[a-zA-Z0-9_]+$", value):
                    print("Invalid GEO ID")
                    return False
            elif validation_type == 'gsm_ids':
                for gsm_id in value:
                    if not re.match(r"^[a-zA-Z0-9_]+$", gsm_id):
                        print("Invalid GSM IDs")
                        return False
            elif validation_type == 'file_path':
                if ".." in value:
                    print(value)
                    print("Invalid file_path")
                    return False
                allowed_chars = re.compile(r"^[a-zA-Z0-9_\-\\/\.]+$")
                if not allowed_chars.match(value):
                    print(value)
                    print("Invalid file_path")
                    return False
            elif validation_type == 'page':
                if not isinstance(value, int) or value < 1:
                    print("Invalid page")
                    return False
            elif validation_type == 'uuid':
                if not re.match(r"^[a-fA-F0-9\-]{36}$", value):
                    print("Invalid uuid")
                    return False
            else:
                return False
        return True

    async def get_series_details_w_gsms(self, gse_id, page=1, per_page=10):
        if not self.validate_parameters([(gse_id, 'gse_id'), (page, 'page'), (per_page, 'page')]):
            return await render_template('information.html', message="Invalid parameters")

        gse_and_gsm = await self.data_service.get_series_details_w_gsms(gse_id)
        if gse_and_gsm:
            return await render_template('series_details.html', info=gse_and_gsm)
        else:
            return await render_template('information.html')

    async def get_gsm_details_by_id(self, gsm_id):
        if not self.validate_parameters([(gsm_id, 'gsm_id')]):
            return await render_template('information.html', message="Invalid parameters")

        specific_gsm_details = await self.data_service.get_gsm_details_by_id(gsm_id)
        if specific_gsm_details:
            return await render_template('gsm_details.html', gsm_details=specific_gsm_details)
        else:
            return await render_template('information.html')

    async def platform(self):
        gpl_info = await self.data_service.get_gpl_with_gses()

        gpl_info_list = list(gpl_info.items())

        return await render_template('platform.html', gpl_info=gpl_info_list)

    async def platform_details(self, gpl_id):
        if not self.validate_parameters([(gpl_id, 'gpl_id')]):
            return await render_template('information.html', message="Invalid parameters")

        specific_platform = await self.data_service.get_gpl_with_gses(gpl_id)
        if specific_platform and gpl_id in specific_platform:
            platform_data = specific_platform[gpl_id]
            return await render_template('platform_details.html', gpl_info=platform_data)
        else:
            return await render_template('information.html', message="No specific platform data found.")

    async def series_import_get(self):
        return await render_template('series_import.html')

    async def series_import_post(self, request):
        try:
            form = await request.form
            gse_id = form.get('gse_id')

            await self.scanner.scan_gse(gse_id=gse_id)

            if not self.validate_parameters([(gse_id, 'gse_id')]):
                return await render_template('series_import.html', message="Invalid parameters")

            return redirect(url_for('import_samples_page', gse_id=gse_id))
        except Exception as e:
            return await render_template('series_import.html', message=str(e))

    async def import_samples_page(self, gse_id):
        try:
            file_path, platform_id = await self.data_service.get_file_path_and_platform_id(gse_id)
            data, data_samples, gse_id_in_db, _, columns_info, show_filter_checkbox = await self.data_service.read_data(gse_id, file_path)

            import_id = await self.loader.get_ongoing_import_id(gse_id)
            ongoing_import = import_id is not None

            if not import_id:
                import_id = str(uuid.uuid4())

            return await render_template('import.html', 
                                        message="GSE Import Page", 
                                        data=data, 
                                        data_samples=data_samples,
                                        gse_id_in_db=gse_id_in_db, 
                                        gse_id=gse_id, 
                                        platform_id=platform_id,
                                        import_id=import_id, 
                                        ongoing_import=ongoing_import,
                                        columns_info=columns_info,
                                        show_filter_checkbox=show_filter_checkbox)
        except Exception as e:
            print(f"Error in import_samples_page: {e}")
            return await render_template('information.html', message=str(e))


    async def start_import(self, gse_id, sample_ids, import_id, filter_p_value=False):
        if not self.validate_parameters([(gse_id, 'gse_id'), (sample_ids, 'gsm_ids'), (import_id, 'uuid')]):
            return jsonify(status='error', message="Invalid parameters")

        try:
            file_path, platform_id = await self.data_service.get_file_path_and_platform_id(gse_id)
            await self.loader.start_import(file_path, platform_id, gse_id, sample_ids, import_id, filter_p_value)

            return jsonify(status='success', import_id=import_id)
        except Exception as e:
            return jsonify(status='error', message=str(e))

    async def get_import_status(self, import_id):
        if not self.validate_parameters([(import_id, 'uuid')]):
            return {
                "status": "unknown",
                "message": "No status available for this import ID.",
                "progress": 0,
                "details": {}
            }
        return await self.loader.get_import_status(import_id)

    # ======================== Group Management ========================

    async def add_group(self, name, short_name):
        result = await self.data_service.add_group(name, short_name)
        return result

    async def remove_group(self, group_id):
        await self.data_service.remove_group(group_id)

    async def assign_sample_to_group(self, sample_id, group_id):
        await self.data_service.assign_sample_to_group(sample_id, group_id)

    async def edit_series_page(self, gse_id):
        series_details = await self.data_service.get_series_details_w_gsms(gse_id)
        groups = await self.data_service.get_groups()
        sample_group_assignments = await self.data_service.get_sample_group_assignments(gse_id)
        tissue_types = await self.data_service.get_tissue_types()

        group_assignments = {sga['sample_id']: sga['group_id'] for sga in sample_group_assignments}

        for sample in series_details['Sample Data']:
            sample['group_id'] = group_assignments.get(sample['id'], None)

        return await render_template('edit_series.html', info=series_details, groups=groups, tissue_types=tissue_types)


    # ======================== Ending of Group Management ========================

    async def update_bto(self, gse_id, bto_id):
        await self.data_service.update_series_bto(gse_id, bto_id)
        
    async def update_tissue_type_series(self, gse_id, tissue_type):
        await self.data_service.update_tissue_type_series(gse_id, tissue_type)

    async def get_export_history(self, user_id):
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor(aiomysql.DictCursor)
        await cursor.execute("SELECT * FROM ExportHistory WHERE user_id = %s ORDER BY id DESC", (user_id,))
        history = await cursor.fetchall()
        await cursor.close()
        await self.db_manager.release_connection(conn)
        return await render_template('export_history.html', history=history)
    
    async def api_export(self, request):
        try:
            data = await request.get_json()
            sample_list = data.get('sample_list', [])
            normalization_method = data.get('normalization_method', 'none')
            log_transform = data.get('logTransform', False)

            print(f"sample_list: {sample_list}")
            print(f"normalization_method: {normalization_method}")
            print(f"log_transform: {log_transform}")

            if not sample_list:
                return jsonify({'error': 'Sample list is required'}), 400

            gene_expression_csv_data, metadata_csv_data, missing_samples = await self.geo_export.export_csv(
                sample_list, normalization_method, log_transform, api_call=True
            )

            if gene_expression_csv_data is None or metadata_csv_data is None:
                return jsonify({'error': 'Failed to generate CSV data', 'missing_samples': missing_samples}), 500

            response_data = {
                "metadata": metadata_csv_data,
                "gene_expression": gene_expression_csv_data,
                "missing_samples": missing_samples
            }

            return jsonify(response_data)

        except Exception as e:
            print(f"Error in api_export_csv: {e}")
            return jsonify({'error': str(e)}), 500
        

    async def add_tissue_type(self, name):
        result = await self.data_service.add_tissue_type(name)
        return result

    async def remove_tissue_type(self, tissue_type_id):
        await self.data_service.remove_tissue_type(tissue_type_id)

    async def assign_sample_tissue_type(self, sample_id, tissue_type_id):
        await self.data_service.assign_sample_tissue_type(sample_id, tissue_type_id)