# YOUR CODE HERE
def solve():
    n = int(input())
    a = list(map(int, input().split()))
    
    even_max = odd_max = float('-inf')
    even_sum = odd_sum = 0
    
    max_sum = float('-inf')
    
    for i in range(n):
        if i % 2 == 0:
            even_sum = max(a[i], even_sum + a[i])
            even_max = max(even_max, even_sum)
            odd_sum = odd_max + a[i]
        else:
            odd_sum = max(a[i], odd_sum + a[i])
            odd_max = max(odd_max, odd_sum)
            even_sum = even_max + a[i]
        
        max_sum = max(max_sum, even_sum, odd_sum)
    
    return max_sum

t = int(input())
for _ in range(t):
    print(solve())