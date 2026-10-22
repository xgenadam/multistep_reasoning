# YOUR CODE HERE
def max_participants():
    N = int(input())
    bases = []
    for _ in range(N):
        W, X = map(int, input().split())
        bases.append((W, X))

    max_employees = 0
    for start_time in range(24):
        end_time = (start_time + 1) % 24
        current_employees = 0
        for W, X in bases:
            local_start = (start_time - X) % 24
            local_end = (end_time - X) % 24
            if local_start < local_end:
                if 9 <= local_start < 18 and 9 <= local_end <= 18:
                    current_employees += W
            else:
                if (9 <= local_start < 24 and 0 <= local_end <= 18) or (9 <= local_start < 18):
                    current_employees += W
        max_employees = max(max_employees, current_employees)

    print(max_employees)

max_participants()