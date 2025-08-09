import aiomysql
from services.geo_data_handler import GEODataHandler
from services.geo_data_import import GEODataImport
from quart import g
from pymysql.err import IntegrityError


class GEODataService:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.geo_data_import = GEODataImport(db_manager)

    async def ensure_connected(self):
        await self.db_manager.ensure_connected()

    async def read_data(self, gse_id, file_path):
        # Check if GSE ID exists in DB and get metadata
        data, gse_in_db = await self.check_gse_id_in_db_and_return(gse_id, file_path)
        
        platform_id = data['Platform-ID']
        samples_to_import = await self.geo_data_import.check_sample_id_table(platform_id, series_id=gse_id, file_path=file_path)

        sample_data_in_db = {}
        gsms = GEODataHandler.get_sample_metadata(file_path)

        columns_info = set()

        # Flag to track if any 'DETECTION P-VALUE' column exists
        show_filter_checkbox = False

        # Iterate through metadata to check columns 
        for sample_id, gsm in gsms.items():
            for column_name, column_info in gsm.get('columns', {}).items():
                columns_info.add((column_name, column_info))
                
                
                if column_name == 'DETECTION P-VALUE':
                    show_filter_checkbox = True

            sample_data_in_db[sample_id] = {
                "Sample ID": sample_id,
                "Title": GEODataHandler.clean_value(gsm, 'title'),
                "Type": GEODataHandler.clean_value(gsm, 'type'),
                "Description": GEODataHandler.clean_value(gsm, 'description'),
                "Contact Email": GEODataHandler.clean_value(gsm, 'contact_email'),
                "Imported": True if sample_id not in samples_to_import else False
            }

        data["Samples Count"] = len(gsms)
        print("show_filter_checkbox", show_filter_checkbox)

        return data, sample_data_in_db, gse_in_db, platform_id, columns_info, show_filter_checkbox

    
    async def update_series_status(self, gse_id, is_finished):
        query = "UPDATE Series SET is_finished = %s WHERE id = %s"
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, (is_finished, gse_id))
            await conn.commit()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    # TODO: Muss man hier is finished betrachten?
    async def check_gse_id_in_db_and_return(self, gse_id, file_path=None):
        query = """
        SELECT 
            s.id, s.title, s.pubmed_id, g.platform_organism, g.platform_taxid, g.platform_manufacturer, 
            g.platform_description, s.series_contact_email, g.id AS platform_id
        FROM 
            Series s
        JOIN 
            Platform g ON s.platform_id = g.id
        WHERE 
            s.id = %s
        """
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, (gse_id,))
            result = await cursor.fetchone()
            if result:
                return {
                    "GSE-ID": result[0],  
                    "GSE-Title": result[1], 
                    "PubMed-ID": result[2], 
                    "Platform-ID": result[8], 
                    "Platform Manufacturer": result[5],  
                    "Platform Organism": result[3] + ", " + result[4], 
                    "Platform Taxid": result[4],  
                    "Platform Description": result[6],  
                    "Platform Contact Email": result[7], 
                }, True
            else:
                return GEODataHandler.default_data(file_path), False
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def get_series_details_w_gsms(self, gse_id):
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            # Fetch series status
            await cursor.execute("SELECT is_finished FROM Series WHERE id = %s", (gse_id,))
            series_status = await cursor.fetchone()

            if not series_status:
                return None

            is_finished = series_status[0]
            try:
                user_role = g.user['role']
            except KeyError:
                user_role = 'guest'

            if user_role not in ['datamanager', 'admin'] and not is_finished:
                return None

            # Fetch series details
            await cursor.execute("""
            SELECT 
                Series.id, Series.title, Series.summary, Series.pubmed_id, Series.type, 
                Series.series_contact_email, Series.platform_id, Series.bto_id, Series.tissue_type,
                COUNT(DISTINCT Sample.id) AS samples_count
            FROM 
                Series
            LEFT JOIN 
                SampleSeries ON Series.id = SampleSeries.series_id
            LEFT JOIN 
                Sample ON SampleSeries.sample_id = Sample.id
            WHERE 
                Series.id = %s
            GROUP BY 
                Series.id
            """, (gse_id,))
            result = await cursor.fetchone()

            # Fetch samples and join tissue_types
            await cursor.execute("""
            SELECT 
                DISTINCT s.id, s.title, s.type, s.description, sg.disease, sg.subtype,
                s.tissue_type_id, tt.name AS tissue_type_name
            FROM 
                Sample s
            LEFT JOIN 
                SampleSeries ss ON s.id = ss.sample_id
            LEFT JOIN 
                sample_group_assignments sga ON s.id = sga.sample_id
            LEFT JOIN 
                sample_groups sg ON sga.group_id = sg.id
            LEFT JOIN
                tissue_types tt ON s.tissue_type_id = tt.id
            WHERE 
                ss.series_id = %s
            """, (gse_id,))

            samples = await cursor.fetchall()
            sample_data = []

            for row in samples:
                sample_data.append({
                    "id": row[0],
                    "title": row[1],
                    "type": row[2],
                    "description": row[3],
                    "disease": row[4] if row[4] else "n/a",
                    "subtype": row[5] if row[5] else "",
                    "tissue_type_id": row[6],
                    "tissue_type_name": row[7] if row[7] else "n/a"
                })

            if result:
                return {
                "Platform-ID": result[6],  
                "GSE-ID": result[0],
                "GSE-Title": result[1],
                "GSE Summary": result[2],
                "PubMed-ID": result[3],  
                "GSE Type": result[4],   
                "Series Contact Email": result[5],  
                "BTO-ID": result[7],  
                "Tissue Type": result[8],  
                "Samples Count": result[9],  
                "Sample Data": sample_data,
                "is_finished": is_finished
                }
            else:
                return None
        except aiomysql.Error as e:
            print("Database error:", e)
            return None
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)



    async def get_gpl_with_gses(self, gpl_id=None):
        try:
            user_role = g.user['role']  # Get user role
        except KeyError:
            user_role = 'guest'

        if user_role in ['datamanager', 'admin']:
            # For datamanager and Admin, join all series and count all series
            series_join = "LEFT JOIN Series s ON g.id = s.platform_id"
            series_count_query = "(SELECT COUNT(*) FROM Series WHERE platform_id = g.id)"  
        else:
            # For regular users, only join finished series and count only finished series
            series_join = "LEFT JOIN Series s ON g.id = s.platform_id AND s.is_finished = TRUE"
            series_count_query = "(SELECT COUNT(*) FROM Series WHERE platform_id = g.id AND is_finished = TRUE)"  

        base_query = f"""
        SELECT 
            g.id AS gpl_id, 
            g.title,
            g.geo_accession,
            g.platform_organism,
            g.platform_taxid,
            g.platform_manufacturer,
            g.platform_description, 
            g.platform_contact_email,
            s.id AS gse_id,
            s.title AS series_title,
            s.summary AS series_summary,
            s.type AS series_type,
            {series_count_query} AS series_count,  
            (SELECT COUNT(*) 
            FROM SampleSeries ss
            JOIN Sample sa ON ss.sample_id = sa.id
            WHERE ss.series_id = s.id) AS sample_count
        FROM 
            Platform g
        {series_join}  
        """

        conditions = []

        if gpl_id:
            conditions.append("g.id = %s")

        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)

        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            if gpl_id:
                await cursor.execute(base_query, (gpl_id,))
            else:
                await cursor.execute(base_query)

            rows = await cursor.fetchall()

            gpl_info = {}
            for row in rows:
                platform_id = row[0]
                if platform_id not in gpl_info:
                    gpl_info[platform_id] = {
                        'title': row[1],
                        'geo_accession': row[2],
                        'platform_organism': row[3],
                        'platform_taxid': row[4], 
                        'platform_organism_taxid': row[3] + ", " + row[4],
                        'platform_manufacturer': row[5],
                        'platform_description': row[6],
                        'platform_contact_email': row[7],
                        'series_count': row[12],  
                        'samples_count': 0,  
                        'gse_ids': []  
                    }

                # Add series data if it exists (based on finished status for non-admins)
                if row[8]:  # row[8] is the series ID (gse_id)
                    gpl_info[platform_id]['gse_ids'].append({
                        'gse_id': row[8],
                        'series_title': row[9],
                        'series_summary': row[10],
                        'series_type': row[11],
                        'sample_count': row[13]  
                    })
                    gpl_info[platform_id]['samples_count'] += row[13]

            return gpl_info
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def get_gsm_details_by_id(self, gsm_id):
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute("""
                SELECT 
                    s.platform_id, 
                    GROUP_CONCAT(ss.series_id) AS series_ids, 
                    s.id, 
                    s.title, 
                    s.type, 
                    s.description, 
                    s.sample_contact_email,
                    s.source_name_ch1,
                    s.organism_ch1,
                    s.taxid_ch1,
                    s.characteristics_ch1,
                    s.molecule_ch1,
                    s.extract_protocol_ch1,
                    s.label_ch1,
                    s.label_protocol_ch1,
                    s.hyb_protocol,
                    s.scan_protocol,
                    s.data_processing
                FROM 
                    Sample s
                JOIN 
                    SampleSeries ss ON s.id = ss.sample_id
                WHERE 
                    s.id = %s
                GROUP BY
                    s.platform_id, s.id, s.title, s.type, s.description, s.sample_contact_email,
                    s.source_name_ch1, s.organism_ch1, s.taxid_ch1, s.characteristics_ch1,
                    s.molecule_ch1, s.extract_protocol_ch1, s.label_ch1, s.label_protocol_ch1,
                    s.hyb_protocol, s.scan_protocol, s.data_processing
            """, (gsm_id,))
            result = await cursor.fetchone()

            if result:
                return {
                    "Platform-ID": result[0],
                    "Series-IDs": result[1].split(','), 
                    "Sample-ID": result[2],
                    "Title": result[3],
                    "Type": result[4],
                    "Description": result[5],
                    "Contact Email": result[6],
                    "Source Name CH1": result[7],
                    "Organism CH1": result[8],
                    "Taxid CH1": result[9],
                    "Characteristics CH1": result[10],
                    "Molecule CH1": result[11],
                    "Extract Protocol CH1": result[12],
                    "Label CH1": result[13],
                    "Label Protocol CH1": result[14],
                    "Hyb Protocol": result[15],
                    "Scan Protocol": result[16],
                    "Data Processing": result[17]
                }
            else:
                return None
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)


    async def get_file_path_and_platform_id(self, gse_id):
        query = "SELECT file_location, platform_id FROM FileLocation WHERE series_id = %s"
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, (gse_id,))
            result = await cursor.fetchone()
            if result:
                file_path, platform_id = result
                return file_path, platform_id
            else:
                raise ValueError(f"No data found for GSE ID: {gse_id}")
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)
            
    #================== Edit ===========================
    async def get_groups(self):
        query = "SELECT id, disease, subtype FROM sample_groups"
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor(aiomysql.DictCursor)
        try:
            await cursor.execute(query)
            return await cursor.fetchall()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)


    async def add_group(self, name, short_name):
        query = "INSERT INTO sample_groups (disease, subtype) VALUES (%s, %s)"
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, (name, short_name))
            await conn.commit()
            return {"status": "success", "message": "Group added successfully."}
        except IntegrityError as e:
            if e.args[0] == 1062:  # Duplicate entry error code
                return {"status": "error", "message": f"Group with the combination of name '{name}' and short name '{short_name}' already exists."}
            else:
                return {"status": "error", "message": "An error occurred while adding the group."}
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def remove_group(self, group_id):
        query = "DELETE FROM sample_groups WHERE id = %s"
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, (group_id,))
            await conn.commit()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def assign_sample_to_group(self, sample_id, group_id):
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute("""
                DELETE FROM sample_group_assignments
                WHERE sample_id = %s
            """, (sample_id,))

            if group_id is not None:
                await cursor.execute("""
                    INSERT INTO sample_group_assignments (sample_id, group_id)
                    VALUES (%s, %s)
                """, (sample_id, group_id))
            
            await conn.commit()
        except aiomysql.Error as e:
            print(f"Error updating sample group assignment: {e}")
            await conn.rollback() 
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def get_sample_group_assignments(self, gse_id):
        query = """
        SELECT s.id AS sample_id, s.title, sga.group_id
        FROM Sample s
        JOIN SampleSeries ss ON s.id = ss.sample_id
        LEFT JOIN sample_group_assignments sga ON s.id = sga.sample_id
        WHERE ss.series_id = %s
        """
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor(aiomysql.DictCursor)
        try:
            await cursor.execute(query, (gse_id,))
            return await cursor.fetchall()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def update_series_bto(self, gse_id, bto_id):
        query = "UPDATE Series SET bto_id = %s WHERE id = %s"
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, (bto_id, gse_id))
            await conn.commit()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def update_tissue_type_series(self, gse_id, tissue_type):
        #TODO: 
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute("""
                UPDATE Series SET tissue_type = %s WHERE id = %s
            """, (tissue_type, gse_id))
            await conn.commit()
        except Exception as e:
            print(f"Error updating tissue type: {e}")
            await conn.rollback()
            return {'error': 'Failed to update tissue type'}
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

        return {'success': 'Tissue type updated successfully'}
        
        # Get all available tissue types
    async def get_tissue_types(self):
        query = "SELECT id, name FROM tissue_types"
        conn = await self.db_manager.get_read_connection()
        cursor = await conn.cursor(aiomysql.DictCursor)
        try:
            await cursor.execute(query)
            return await cursor.fetchall()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def add_tissue_type(self, name):
        query = "INSERT INTO tissue_types (name) VALUES (%s)"
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, (name,))
            await conn.commit()
        except IntegrityError as e:
            if e.args[0] == 1062:
                return {"status": "error", "message": f"Tissue type '{name}' already exists."}
            else:
                return {"status": "error", "message": "An error occurred while adding the tissue type."}
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)
        return {"status": "success", "message": "Tissue type added successfully."}

    async def remove_tissue_type(self, tissue_type_id):
        query = "DELETE FROM tissue_types WHERE id = %s"
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            await cursor.execute(query, (tissue_type_id,))
            await conn.commit()
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)

    async def assign_sample_tissue_type(self, sample_id, tissue_type_id):
        conn = await self.db_manager.get_write_connection()
        cursor = await conn.cursor()
        try:
            if tissue_type_id is None:
                await cursor.execute("""
                    UPDATE Sample 
                    SET tissue_type_id = NULL
                    WHERE id = %s
                """, (sample_id,))
            else:
                await cursor.execute("""
                    UPDATE Sample 
                    SET tissue_type_id = %s
                    WHERE id = %s
                """, (tissue_type_id, sample_id))
            
            await conn.commit()
        except aiomysql.Error as e:
            await conn.rollback()
            print("Error updating tissue_type_id:", e)
        finally:
            await cursor.close()
            await self.db_manager.release_connection(conn)
