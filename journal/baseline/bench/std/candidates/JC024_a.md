class Solution:
    def maximumSubarraySum(self, nums: List[int], k: int) -> int:
        n = len(nums)
        max_sum = float('-inf')
        
        # Create dictionaries to store the first occurrence and sum up to each number
        first_occurrence = {}
        prefix_sum = {}
        current_sum = 0
        
        for i, num in enumerate(nums):
            current_sum += num
            
            # Check if there's a number that differs by k
            if num - k in first_occurrence:
                j = first_occurrence[num - k]
                subarray_sum = current_sum - prefix_sum[j] + nums[j]
                max_sum = max(max_sum, subarray_sum)
            
            if num + k in first_occurrence:
                j = first_occurrence[num + k]
                subarray_sum = current_sum - prefix_sum[j] + nums[j]
                max_sum = max(max_sum, subarray_sum)
            
            # Store the first occurrence and prefix sum
            if num not in first_occurrence:
                first_occurrence[num] = i
                prefix_sum[i] = current_sum
        
        return max_sum if max_sum != float('-inf') else 0