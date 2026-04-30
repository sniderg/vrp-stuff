namespace Roadef_Challenge.util
{
    public static class Floating
    {
        /// <summary>
        /// The epsilon used for floating-point numbers comparisons.</summary>
        ///
        public const double EPSILON = 1e-6f;

        /// <summary>
        /// Returns true if the doubles a and b are equal.</summary>
        /// 
        /// <param name="a">First double to compare.</param>
        /// <param name="b">Second double to compare.</param>
        /// 
        /// <returns>True if the two double are equal, 
        /// false otherwise.</returns>
        /// 
        public static bool Equal(double a, double b)
        {
            return -EPSILON < a - b && a - b < EPSILON;
        }

        /// <summary>
        /// Returns true if the double a is lower or equal 
        /// than the double b (that is, lower than b+epsilon).</summary>
        /// 
        /// <param name="a">First double to compare.</param>
        /// <param name="b">Second double to compare.</param>
        /// 
        /// <returns>True if the double a is lower 
        /// than the double b, false otherwise.</returns>
        /// 
        public static bool Lower(double a, double b)
        {
            return a - b < EPSILON;
        }

        /// <summary>
        /// Returns true if the double a is greater or equal
        /// than the double b (that is, greater than b-epsilon).</summary>
        /// 
        /// <param name="a">First double to compare.</param>
        /// <param name="b">Second double to compare.</param>
        /// 
        /// <returns>True if the double a is greater 
        /// than the double b, false otherwise.</returns>
        /// 
        public static bool Greater(double a, double b)
        {
            return b - a < EPSILON;
        }

        public static bool StrictlyLower(double a, double b) { return !Greater(a, b); }
        public static bool StrictlyGreater(double a, double b) { return !Lower(a, b); }

        /// <summary>
        /// Returns true if the double a is strictly negative.</summary>
        /// 
        /// <param name="a">The double to compare.</param>		
        /// 
        /// <returns>True if the double a is strictly negative.</returns>
        /// 
        public static bool StrictlyNegative(double a)
        {
            return a < -EPSILON;
        }

        /// <summary>
        /// Returns true if the double a is strictly positive.</summary>
        /// 
        /// <param name="a">The double to compare.</param>		
        /// 
        /// <returns>True if the double a is strictly positive.</returns>
        /// 
        public static bool StrictlyPositive(double a)
        {
            return a > EPSILON;
        }

        public static bool Negative(double a) { return !StrictlyPositive(a); }
        public static bool Positive(double a) { return !StrictlyNegative(a); }

    }
}
