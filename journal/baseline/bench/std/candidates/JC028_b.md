# YOUR CODE HERE
def min_cost(N, S, M, L):
    dp = [float('inf')] * (N + 13)
    dp[0] = 0
    
    for i in range(N + 1):
        if i >= 6:
            dp[i] = min(dp[i], dp[i-6] + S)
        if i >= 8:
            dp[i] = min(dp[i], dp[i-8] + M)
        if i >= 12:
            dp[i] = min(dp[i], dp[i-12] + L)
    
    return min(dp[N:])

N, S, M, L = map(int, input().split())
print(min_cost(N, S, M, L))