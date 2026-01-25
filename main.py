import pandas
from bisect import bisect_left

df = pandas.read_excel("data/tab_lhfa_boys_p_0_2.xlsx")
height, age_months = float(input()), int(input())
heights = df[df["Month"] == age_months].iloc[0].values.tolist()[5:]
i = bisect_left(heights, height)
print("Your child's percentile:", df.columns[min(i+5, 19)])