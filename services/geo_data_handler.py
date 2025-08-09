from collections import defaultdict
import os
from re import sub
import numpy as np
import pandas as pd
import GEOparse
import GEOparse.utils
from itertools import groupby
from GEOparse import utils
from pandas import DataFrame

class GEODataHandler:
    '''
    GEOparse.get_GEO(filepath=file_path, partial="none", geotype='GPL', open_kwargs={'mode': 'rt'})         
    Dauer der get_GEO-Funktion: 2,7 Sekunden
    Ohne partial="none"  Dauer der get_GEO-Funktion: 4.95 Sekunden
    
    gpl.metadata: ^PLATFORM bis Columns 
    gpl.columns: #ID bis !platform_table_begin
    
    GEOparse.get_GEO(filepath=file_path, geotype='GSE', open_kwargs={'mode': 'rt'}) 
    Dauer der get_GEO-Funktion: 5.57 Sekunden
    
    get_metadata    Dauer < 1 Sekunde
    
    open_kwargs={'mode': 'rt'} ermöglicht den Zugriff GSE15960_family.soft.gz, ohne es zu entpacken.
    
    '''
    @staticmethod
    def download_GEO_file(gse_id, destdir="temp"):
        gse_dir = os.path.join(destdir, gse_id)

        file_path, _ = GEOparse.get_GEO_file(geo=gse_id, destdir=gse_dir)
        return file_path
            
    @staticmethod
    def extract_gsm_ids(file_path):
        metadata = GEODataHandler.get_metadata(file_path, geotype="series")
        return metadata.get('sample_id', [])
    
    @staticmethod
    def extract_gpl_id(file_path):
        return GEODataHandler.clean_value(GEODataHandler.get_metadata(file_path, geotype="platform"), 'geo_accession')
    
    @staticmethod
    def parse_gpl(file_path, partial=None):
        try:
            open_kwargs = {'mode': 'rt'}
            gse = GEOparse.parse_GPL(file_path, entry_name="PLATFORM", partial=partial, open_kwargs=open_kwargs)
            return gse
        except Exception as e:
            print(f"Error parsing GSE: {e}")
        
    @staticmethod
    def parse_gsm(file_path, partial):
        try:
            open_kwargs = {'mode': 'rt'}
            gpl = GEOparse.parse_GPL(file_path, entry_name="GSM", partial=partial, open_kwargs=open_kwargs)
            return gpl.gsms
        except Exception as e:
            print(f"Error parsing GSE: {e}")

    # kann vereinfacht werden
    def clean_value(data, key=None, is_float=False):
        value = None
        # Check if key exists in data
        if key and key not in data:
            return None if is_float else 'n/a'

        # Get the value from the data
        if key:
            value = data.get(key)
        else:
            value = data

        # If the value is expected to be a float, handle conversion
        if is_float:
            try:
                return float(value)
            except (ValueError, TypeError):
                #print(f"Unable to convert value to float: {value}")
                return None  

        # For non-float values, perform the original handling
        if isinstance(value, float) and np.isnan(value):
            return 'n/a'
        if isinstance(value, list):
            if not value:
                return 'n/a'  
            value = "; ".join(value)  
        if value is None or value == 'None':
            return 'n/a'
        if not isinstance(value, str):
            value = str(value)
        return value.strip()


    @staticmethod
    def prepare_platform_data(file_path):
        metadata = GEODataHandler.get_metadata(file_path, geotype="platform")
        return {
            'platform_id': GEODataHandler.clean_value(metadata, 'geo_accession'),
            'title': GEODataHandler.clean_value(metadata, 'title'),
            'geo_accession': GEODataHandler.clean_value(metadata, 'geo_accession'),
            'platform_organism': GEODataHandler.clean_value(metadata, 'organism'),
            'platform_taxid': GEODataHandler.clean_value(metadata, 'taxid'),
            'platform_manufacturer': GEODataHandler.clean_value(metadata, 'manufacturer'),
            'platform_description': GEODataHandler.clean_value(metadata, 'description'),
            'platform_contact_email': GEODataHandler.clean_value(metadata, 'contact_email')
        }

    @staticmethod
    def prepare_gene_annotations_data(file_path, platform_id):
        soft_gpl = GEODataHandler.parse_gpl(file_path, partial="no")
        #soft_gpl = GEOparse.get_GEO(filepath=file_path)
        #platform_table = list(soft_gpl.gpls.items())[0][1].table
        
        gene_annotations_data = []
        for _, row in soft_gpl.table.iterrows():
            gene_annotations_data.append((
                GEODataHandler.clean_value(row, 'ID'),
                platform_id, 
                GEODataHandler.clean_value(row, 'Gene Title'),
                GEODataHandler.clean_value(row, 'Gene Symbol'),
                GEODataHandler.clean_value(row, 'ENTREZ_GENE_ID'),
                GEODataHandler.clean_value(row, 'RefSeq Transcript ID')
            ))
        return gene_annotations_data

    def prepare_series_data(file_path, gse_id, platform_id):
        print("file_path: ", file_path)
        series_metadata = GEODataHandler.get_metadata(file_path, geotype="series")
        
        pubmed_ids = series_metadata.get('pubmed_id', [])
        if isinstance(pubmed_ids, list):
            pubmed_ids = "; ".join(pubmed_ids)  
        else:
            pubmed_ids = GEODataHandler.clean_value(pubmed_ids)  

        return {
            'gse_id': gse_id,
            'platform_id': platform_id,
            'title': GEODataHandler.clean_value(series_metadata, 'title'),
            'summary': GEODataHandler.clean_value(series_metadata, 'summary'),
            'pubmed_id': pubmed_ids,  
            'type': GEODataHandler.clean_value(series_metadata, 'type'),
            'series_contact_email': GEODataHandler.clean_value(series_metadata, 'contact_email')
        }

    @staticmethod
    def prepare_sample_data(file_path):
        metadata = GEODataHandler.get_sample_metadata(file_path, entries=None, open_kwargs=None)
        
        prepared_samples = []
        
        for sample_id, data in metadata.items():
            
            sample = {
                'sample_id': sample_id,
                'sample_series_id': GEODataHandler.clean_value(data, 'series_id'),
                'platform_id': GEODataHandler.clean_value(data, 'platform_id'),
                'title': GEODataHandler.clean_value(data, 'title'),
                'type': GEODataHandler.clean_value(data, 'type'),
                'description': GEODataHandler.clean_value(data, 'description'),
                'sample_contact_email': GEODataHandler.clean_value(data, 'contact_email'),
                'source_name_ch1': GEODataHandler.clean_value(data, 'source_name_ch1'),
                'organism_ch1': GEODataHandler.clean_value(data, 'organism_ch1'),
                'taxid_ch1': GEODataHandler.clean_value(data, 'taxid_ch1'),
                'characteristics_ch1': GEODataHandler.clean_value(data, 'characteristics_ch1'),
                'molecule_ch1': GEODataHandler.clean_value(data, 'molecule_ch1'),
                'extract_protocol_ch1': GEODataHandler.clean_value(data, 'extract_protocol_ch1'),
                'label_ch1': GEODataHandler.clean_value(data, 'label_ch1'),
                'label_protocol_ch1': GEODataHandler.clean_value(data, 'label_protocol_ch1'),
                'hyb_protocol': GEODataHandler.clean_value(data, 'hyb_protocol'),
                'scan_protocol': GEODataHandler.clean_value(data, 'scan_protocol'),
                'data_processing': GEODataHandler.clean_value(data, 'data_processing')
            }
            prepared_samples.append(sample)

        return prepared_samples

      
    @staticmethod
    def default_data(file_path):
        try:
            series_metadata = GEODataHandler.get_metadata(file_path, geotype="series")
            platform_metadata = GEODataHandler.get_metadata(file_path, geotype="platform")
        except Exception as e:
            print("ERROR: ", e)
            return None
                    
        pubmed_ids = series_metadata.get('pubmed_id', [])
        if isinstance(pubmed_ids, list):
            pubmed_ids = "; ".join(pubmed_ids)  
        else:
            pubmed_ids = GEODataHandler.clean_value(pubmed_ids)  

        return {
            "GSE-ID": series_metadata.get('geo_accession', [''])[0],
            "GSE-Title": series_metadata.get('title', [''])[0],
            "PubMed-ID": pubmed_ids,  
            "Platform-ID": platform_metadata.get('geo_accession', [''])[0],
            "Platform Manufacturer": GEODataHandler.clean_value(platform_metadata, 'manufacturer'),
            "Platform Organism": GEODataHandler.clean_value(platform_metadata, 'organism') + " " + GEODataHandler.clean_value(platform_metadata, 'taxid'),
            "Platform Taxid": GEODataHandler.clean_value(platform_metadata, 'taxid'),
            "Platform Description": GEODataHandler.clean_value(platform_metadata, 'description'),
            "Platform Contact Email": GEODataHandler.clean_value(platform_metadata, 'contact_email')
        }


    # aus geo parse kommentiere
    def __parse_entry(entry_line):
        """
        Direkt aus GEOparse übernommen.
        
        Parse the SOFT file entry name line that starts with '^', '!' or '#'.

        Args:
            entry_line (:obj:`str`): Line from SOFT  to be parsed.

        Returns:
            :obj:`2-tuple`: Type of entry, value of entry.

        """
        if entry_line.startswith("!"):
            entry_line = sub(r"!\w*?_", "", entry_line)
        else:
            entry_line = entry_line.strip()[1:]
        try:
            entry_type, entry_name = [i.strip() for i in entry_line.split("=", 1)]
        except ValueError:
            entry_type = [i.strip() for i in entry_line.split("=", 1)][0]
            entry_name = ""
        return entry_type, entry_name
    
    
    def parse_metadata(lines):
        """
        Parse list of lines with metadata information from SOFT file.

        Args:
            lines (:obj:`Iterable`): Iterator over the lines.

        Returns:
            :obj:`dict`: Metadata from SOFT file, including columns.
        """
        meta = defaultdict(list)
        columns = {}

        for line in lines:
            line = line.rstrip()
            if line.startswith("#"):
                key, value = GEODataHandler.__parse_entry(line)
                columns[key] = value  
            elif line.startswith("!"):
                if "_table_begin" in line or "_table_end" in line:
                    continue
                key, value = GEODataHandler.__parse_entry(line)
                meta[key].append(value)

        # Add columns to metadata
        if columns:
            meta["columns"] = columns
        
        return dict(meta)
    
        
    @staticmethod
    def get_sample_metadata(filepath, entries=None, open_kwargs=None):
        if open_kwargs is None:
            open_kwargs = {'mode': 'rt', 'encoding': 'utf-8'}

        metadata = {}

        try:
            with utils.smart_open(filepath, **open_kwargs) as soft:
                group_iterator = groupby(soft, lambda x: x.startswith("^"))
                for is_new_entry, group in group_iterator:
                    if is_new_entry:
                        entry_type, entry_name = GEODataHandler.__parse_entry(next(group))
                        if entry_type.lower() == "sample":
                            if entries is None or entry_name in entries:
                                is_data, data_group = next(group_iterator, (None, []))
                                assert not is_data, "There is an error in the SOFT file"
                                metadata[entry_name] = GEODataHandler.parse_metadata(data_group)
                                        
        except Exception as e:
            print(f"Error while parsing GSM metadata: {e}")
        
        return metadata

    @staticmethod
    def get_metadata(filepath, open_kwargs=None, geotype=None, modus=None):
        """
        Modified version from GEOparse that is used in parse_gpl and others to directly extract metadata.
        """
        if open_kwargs is None:
            open_kwargs = {'mode': 'rt', 'encoding': 'utf-8'}
            
        allowed_types = {"series", "database", "platform"}
        if geotype not in allowed_types:
            raise ValueError(f"Invalid geotype provided. Allowed types are: {allowed_types}")

        metadata = {}
        
        try:
            with utils.smart_open(filepath, **open_kwargs) as soft:
                group_iterator = groupby(soft, lambda x: x.startswith("^"))
                for is_new_entry, group in group_iterator:
                    if is_new_entry:
                        entry_type, entry_name = GEODataHandler.__parse_entry(next(group))
                        entry_type = entry_type.lower()
                        if entry_type == geotype:
                            is_data, data_group = next(group_iterator, (None, []))
                            assert not is_data, "There is an error in the SOFT file"
                            if modus == "columns":
                                return GEODataHandler.parse_columns(data_group)
                            else:
                                metadata = GEODataHandler.parse_metadata(data_group)
                                break
        except Exception as e:
            print(f"Error while parsing metadata: {e}")

        return metadata

    def parse_columns(lines, gsm=False):
        """
        Aus GEoparse übernommen
        
        Parse list of lines with columns description from SOFT file.

        Args:
            lines (:obj:`Iterable`): Iterator over the lines.

        Returns:
            :obj:`pandas.DataFrame`: Columns description.

        """
        data = []
        index = []
        for line in lines:
            line = line.rstrip()
            if line.startswith("#"):
                tmp = GEODataHandler.__parse_entry(line)
                data.append(tmp[1])
                index.append(tmp[0])

        if gsm:
            return DataFrame(data, index=index, columns=["description"]).to_dict()
        else:
            return DataFrame(data, index=index, columns=["description"])
