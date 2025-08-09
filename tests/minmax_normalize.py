import numpy as np

class NormalizationTest:
    def minmax_normalize(self, values):
        """
        Min-Max-Normalisierung, bei der der kleinste Wert auf 0 und der größte Wert auf 1 skaliert wird.
        Liefert auch Min- und Maxwerte zurück, um sie in die Metadaten aufzunehmen.
        """
        if len(values) == 0:
            return np.nan, np.nan, np.nan  

        min_val = np.min(values)
        max_val = np.max(values)

        if max_val == min_val:
            return np.zeros_like(values), min_val, max_val 

        return (values - min_val) / (max_val - min_val), min_val, max_val

def print_result(description, result, expected_min, expected_max):
    normalized_values, min_val, max_val = result
    is_min_correct = min_val == expected_min
    is_max_correct = max_val == expected_max
    print(f"{description}: {result}")
    print(f"Min korrekt: {is_min_correct}, Max korrekt: {is_max_correct}")
    print("-" * 50 + "\n")


test_instance = NormalizationTest()

values4 = np.array([-1, 0, 1])
result4 = test_instance.minmax_normalize(values4)
print_result("Test 1 (Array mit negativen Werten)", result4, -1, 1)

values5 = np.array([10, 23, 15, 7, 30, 18, 25, 9, 16, 22, 3, 29, 11, 21, 19, 13, 27, 5, 20, 24])
result5 = test_instance.minmax_normalize(values5)
print_result("Test 2 (Array mit gemischten Werten)", result5, 3, 30)

values6 = np.array([100, 250, 150, 70, 300, 180, 225, 90, 160, 220, 30, 290, 110, 210, 190, 130, 270, 50, 200, 240])
result6 = test_instance.minmax_normalize(values6)
print_result("Test 3 (Array mit größeren Werten)", result6, 30, 300)

values7 = np.array([-100, 0, 50, -25, 100, 75, -50, 25, -75, -10, 60, -30, 15, -20, 80, -5, 90])
result7 = test_instance.minmax_normalize(values7)
print_result("Test 4 (Array mit negativen und positiven Werten)", result7, -100, 100)

values8 = np.array([1.001, 1.002, 1.003, 1.004, 1.0005, 1.0008, 1.0015, 1.0025])
result8 = test_instance.minmax_normalize(values8)
print_result("Test 5 (Array mit kleinen Unterschieden)", result8, 1.0005, 1.004)
