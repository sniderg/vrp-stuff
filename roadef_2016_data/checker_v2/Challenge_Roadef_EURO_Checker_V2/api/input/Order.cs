using System;

namespace Roadef_Challenge.api.input
{
    /// <summary>
    /// Order for a customer.
    /// </summary>
    [Serializable]
    public class Order 
    {

        //int OrderIndex;

        /// <summary>
        /// The quantity to be delivered to this client.
        /// </summary>
        public double Quantity { get; set; }

        /// <summary>
        /// The earliest time for the delivery to take place.
        /// </summary>
        public int earliestTime;

        /// <summary>The latest time for the delivery to take place.</summary>
        /// 
        public int latestTime;

        /// <summary> 
        /// The percentage (in base 100) of flexibility allowed to satisfy the order quantity.
        /// Must be between 0 and 100.
        /// </summary>
        public int orderQuantityFlexibility;

        /// <summary>
        /// Minimum quantity to deliver to satisfy this order.
        /// </summary>
        public double MinQuantityToSatisfy { get { return Quantity * orderQuantityFlexibility / 100; } }

        /// <summary>
        /// Shallow copy of this order.
        /// </summary>
        /// <returns>A new object with same values for each field (NOT a deep copy).</returns>
        public Order ShallowCopy()
        {
            return (Order)MemberwiseClone();
        }

        /// <summary>
        /// Printer.
        /// </summary>
        /// <returns>String representation of the order.</returns>
        public override string ToString()
        {
            return Quantity + "@[" + earliestTime + "," + latestTime + "]";
        }
    }
}
