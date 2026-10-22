class Solution:
    def minimumOperations(self, num: str) -> int:
        n = len(num)
        
        # Check if the number is already 0
        if num == "0":
            return 0
        
        # Find the rightmost '0' and '5'
        last_zero = num.rfind('0')
        last_five = num.rfind('5')
        
        # Initialize the minimum operations to delete all digits
        min_ops = n
        
        # Check for '00', '25', '50', '75'
        if last_zero != -1:
            # Check for another '0' before the last '0'
            second_last_zero = num.rfind('0', 0, last_zero)
            if second_last_zero != -1:
                min_ops = min(min_ops, n - second_last_zero - 2)
            
            # Check for '5' before the last '0'
            five_before_zero = num.rfind('5', 0, last_zero)
            if five_before_zero != -1:
                min_ops = min(min_ops, n - five_before_zero - 2)
        
        if last_five != -1:
            # Check for '2' or '7' before the last '5'
            two_before_five = num.rfind('2', 0, last_five)
            seven_before_five = num.rfind('7', 0, last_five)
            if two_before_five != -1:
                min_ops = min(min_ops, n - two_before_five - 2)
            if seven_before_five != -1:
                min_ops = min(min_ops, n - seven_before_five - 2)
        
        # If no valid combination found, delete all digits except one
        return min(min_ops, n - 1)