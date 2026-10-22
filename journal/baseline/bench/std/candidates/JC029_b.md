# YOUR CODE HERE
N = int(input())
A = list(map(int, input().split()))

total_sum = sum(A)
prefix_sum = [0] * (10**6 + 1)

for num in A:
    prefix_sum[num] += num

for i in range(1, 10**6 + 1):
    prefix_sum[i] += prefix_sum[i-1]

result = []
for num in A:
    result.append(total_sum - prefix_sum[num])

print(*result)