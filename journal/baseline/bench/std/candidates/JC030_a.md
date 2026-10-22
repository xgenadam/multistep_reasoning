# YOUR CODE HERE
from itertools import permutations

def read_grid(H, W):
    return [list(map(int, input().split())) for _ in range(H)]

def is_identical(grid1, grid2):
    return all(row1 == row2 for row1, row2 in zip(grid1, grid2))

def min_operations(A, B):
    H, W = len(A), len(A[0])
    
    row_perm = list(permutations(range(H)))
    col_perm = list(permutations(range(W)))
    
    min_ops = float('inf')
    
    for row_p in row_perm:
        for col_p in col_perm:
            temp_A = [[A[i][j] for j in col_p] for i in row_p]
            if is_identical(temp_A, B):
                row_ops = sum(i != j for i, j in enumerate(row_p))
                col_ops = sum(i != j for i, j in enumerate(col_p))
                min_ops = min(min_ops, row_ops + col_ops)
    
    return min_ops if min_ops != float('inf') else -1

H, W = map(int, input().split())
A = read_grid(H, W)
B = read_grid(H, W)

result = min_operations(A, B)
print(result)