import pytest
import numpy as np
from collections import defaultdict

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

#geo_export.py
from services.geo_export import GEOExport


# python -m pytest tests/unittest/test_quantil.py

class MockCursor:
    def __init__(self, data):
        self.data = data

    async def execute(self, query, params):
        pass

    async def fetchall(self):
        return self.data

    async def close(self):
        pass

class MockDBManager:
    async def get_read_connection(self):
        return self

    async def release_connection(self, conn):
        pass

    async def cursor(self):
        # Mock data structure: (gene_symbol, sample_id, value, series_id, sample_group_name, sample_group_short_name, series_type, bto_id, tissue_type)
        return MockCursor([
            ('GeneA', 'S1', 5.0, 'Series1', 'Group1', 'G1', 'Type1', 'BTO1', 'Tissue1'),
            ('GeneB', 'S1', 6.0, 'Series1', 'Group1', 'G1', 'Type1', 'BTO1', 'Tissue1'),
            ('GeneA', 'S2', 8.0, 'Series1', 'Group1', 'G1', 'Type1', 'BTO1', 'Tissue1'),
            ('GeneB', 'S2', 3.0, 'Series1', 'Group1', 'G1', 'Type1', 'BTO1', 'Tissue1')
        ])

@pytest.fixture
async def geo_export_fixture():
    db_manager = MockDBManager()
    return GEOExport(db_manager)

@pytest.mark.asyncio
async def test_quantile_normalize(geo_export_fixture):
    """
    raw data --> order values within each sample or column --> average across rows and substitute values with the average --> reorder averaged values 
    """
    # ['GeneA', 'GeneB']
    selected_ids = ['S1', 'S2']
    normalization_method = 'quantile'

    print("Starting test for quantile normalization...")

    geo_export = await geo_export_fixture
    
    normalized_samples, sample_to_series, gene_symbol_order, additional_data, normalization_metadata, missing_samples = await geo_export.collect_data_for_export(selected_ids, normalization_method)

    assert len(missing_samples) == 0, f"Expected no missing samples, but got {len(missing_samples)}"
    assert len(normalized_samples) == 2, f"Expected 2 normalized samples, but got {len(normalized_samples)}"

    print(f"Testing values for sample S1, GeneA: Expected ~4.0, Got {normalized_samples['S1']['GeneA']}")
    print(f"Testing values for sample S1, GeneB: Expected ~7.0, Got {normalized_samples['S1']['GeneB']}")
    print(f"Testing values for sample S2, GeneA: Expected ~7.0, Got {normalized_samples['S2']['GeneA']}")
    print(f"Testing values for sample S2, GeneB: Expected ~4.0, Got {normalized_samples['S2']['GeneB']}")

    assert np.isclose(normalized_samples['S1']['GeneA'], 4.0), f"Expected ~4.0 for S1, GeneA, but got {normalized_samples['S1']['GeneA']}"
    assert np.isclose(normalized_samples['S1']['GeneB'], 7.0), f"Expected ~7.0 for S1, GeneB, but got {normalized_samples['S1']['GeneB']}"
    assert np.isclose(normalized_samples['S2']['GeneA'], 7.0), f"Expected ~7.0 for S2, GeneA, but got {normalized_samples['S2']['GeneA']}"
    assert np.isclose(normalized_samples['S2']['GeneB'], 4.0), f"Expected ~4.0 for S2, GeneB, but got {normalized_samples['S2']['GeneB']}"

    print("Quantile normalization test completed successfully.")
