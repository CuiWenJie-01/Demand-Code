# 求斐波那契数列第n项的值
# 0, 1, 1, 2, 3, 5, 8 ... (第0项为0，第一项为1，第二项开始，每项都是前两项的和)
from functools import lru_cache

@lru_cache(maxsize=None)
def fn(n):
    if n<=1:
        return n
    else:
        return fn(n-1)+fn(n-2)

print(fn(100))