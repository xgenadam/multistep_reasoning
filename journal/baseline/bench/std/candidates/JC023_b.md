class Solution:
    def countCompleteSubstrings(self, word: str, k: int) -> int:
        def count_complete(s):
            n = len(s)
            result = 0
            for unique in range(1, 27):
                if unique * k > n:
                    break
                freq = [0] * 26
                left = 0
                count = 0
                for right in range(n):
                    freq[ord(s[right]) - ord('a')] += 1
                    if freq[ord(s[right]) - ord('a')] == k:
                        count += 1
                    while right - left + 1 > unique * k:
                        if freq[ord(s[left]) - ord('a')] == k:
                            count -= 1
                        freq[ord(s[left]) - ord('a')] -= 1
                        left += 1
                    if right - left + 1 == unique * k and count == unique:
                        result += 1
            return result

        n = len(word)
        segments = [0]
        for i in range(1, n):
            if abs(ord(word[i]) - ord(word[i-1])) > 2:
                segments.append(i)
        segments.append(n)

        total = 0
        for i in range(1, len(segments)):
            total += count_complete(word[segments[i-1]:segments[i]])
        
        return total