class Solution:
    def canMakeSubsequence(self, str1: str, str2: str) -> bool:
        def next_char(c):
            return chr((ord(c) - ord('a') + 1) % 26 + ord('a'))
        
        n, m = len(str1), len(str2)
        j = 0
        
        for i in range(n):
            if j < m and (str1[i] == str2[j] or next_char(str1[i]) == str2[j]):
                j += 1
        
        return j == m