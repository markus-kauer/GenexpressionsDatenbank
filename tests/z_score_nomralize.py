import numpy as np

class NormalizationTest:
    def zscore_normalize(self, values):
        """
        """
        if len(values) == 0:
            return np.nan, np.nan, np.nan 

        mean = np.mean(values)
        std = np.std(values)

        if std == 0:
            return np.zeros_like(values), mean, std  

        return (values - mean) / std, mean, std

def print_zscore_result(description, result, expected_mean, expected_std):
    normalized_values, mean_val, std_val = result
    is_mean_correct = np.isclose(mean_val, expected_mean)
    is_std_correct = np.isclose(std_val, expected_std)
    print(f"{description}: {result}")
    print(f"Mittelwert korrekt: {is_mean_correct}, Standardabweichung korrekt: {is_std_correct}")
    print("-" * 50 + "\n")


test_instance = NormalizationTest()

values1 = np.array([10, 23, 15, 7, 30, 18, 25, 9, 16, 22, 3, 29, 11, 21, 19, 13, 27, 5, 20, 24])
result1 = test_instance.zscore_normalize(values1)
print_zscore_result("Test 1 (Array mit gemischten Werten)", result1, np.mean(values1), np.std(values1))

values2 = np.array([100, 250, 150, 70, 300, 180, 225, 90, 160, 220, 30, 290, 110, 210, 190, 130, 270, 50, 200, 240])
result2 = test_instance.zscore_normalize(values2)
print_zscore_result("Test 2 (Array mit größeren Werten)", result2, np.mean(values2), np.std(values2))

values3 = np.array([-100, 0, 50, -25, 100, 75, -50, 25, -75, -10, 60, -30, 15, -20, 80, -5, 90])
result3 = test_instance.zscore_normalize(values3)
print_zscore_result("Test 3 (Array mit negativen und positiven Werten)", result3, np.mean(values3), np.std(values3))

values4 = np.array([1.001, 1.002, 1.003, 1.004, 1.0005, 1.0008, 1.0015, 1.0025])
result4 = test_instance.zscore_normalize(values4)
print_zscore_result("Test 4 (Array mit kleinen Unterschieden)", result4, np.mean(values4), np.std(values4))
