class Solution:
    def maximumSumOfHeights(self, maxHeights: List[int]) -> int:
        n = len(maxHeights)
        
        def calculate_sum(peak):
            left = [0] * n
            right = [0] * n
            stack = []
            
            # Calculate left part
            for i in range(peak + 1):
                while stack and maxHeights[stack[-1]] > maxHeights[i]:
                    stack.pop()
                if not stack:
                    left[i] = (i + 1) * maxHeights[i]
                else:
                    j = stack[-1]
                    left[i] = left[j] + (i - j) * maxHeights[i]
                stack.append(i)
            
            # Reset stack for right part
            stack.clear()
            
            # Calculate right part
            for i in range(n - 1, peak - 1, -1):
                while stack and maxHeights[stack[-1]] > maxHeights[i]:
                    stack.pop()
                if not stack:
                    right[i] = (n - i) * maxHeights[i]
                else:
                    j = stack[-1]
                    right[i] = right[j] + (j - i) * maxHeights[i]
                stack.append(i)
            
            return left[peak] + right[peak] - maxHeights[peak]
        
        return max(calculate_sum(i) for i in range(n))