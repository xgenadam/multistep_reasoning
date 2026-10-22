class Solution:
    def countWays(self, nums: List[int]) -> int:
        n = len(nums)
        nums.sort()
        count = 0
        
        # Check if selecting 0 students is valid
        if nums[0] > 0:
            count += 1
        
        # Check for each possible number of selected students
        for i in range(n):
            selected = i + 1
            if selected > nums[i] and (i == n - 1 or selected < nums[i + 1]):
                count += 1
        
        return count