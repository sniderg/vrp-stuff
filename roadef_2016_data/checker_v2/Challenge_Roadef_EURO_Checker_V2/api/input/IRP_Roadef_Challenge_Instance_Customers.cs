using System;
using System.Collections;


namespace Roadef_Challenge.api.input
{
	/// <summary>A customer and its specific characteristics.</summary>
	/// 
    [Serializable]
    public class IRP_Roadef_Challenge_Instance_Customers 
	{
		#region FIELDS


        /// <summary> The unique index for this point. 
        /// This index is the index of the Point in the array that would 
        /// be obtained by concatenation of bases,sources and customers arrays.</summary>
        /// 
        public int index;

        /// <summary>  if 1 the customer must be served in a shift with a layover, 0 otherwise
        public int LayoverCustomer;

        /// <summary>1 if and only if unsolicited deliveries 
        /// are forbidden for this customer that is to say that 
        /// this customer will only issue orders. consequently
        ///  the attributes forecast, capacity, initialTankQuantity, 
        /// safetyLevel and runoutCost are not relevant 
        /// for these customersByRunoutDate.</summary>
        /// 
        public int callIn;

        /// <summary>A list of orders that is to say pairs with (quantity, time-window).
        ///  each pair represents a request for a delivery of quantity¸ 
        /// taking place within the specified time-window. non-satisfaction 
        /// of orders will be penalized in the objective function.</summary>
        /// 
        public Order[] orders;


        /// <summary> the forecasted consumption or production of 
        /// customer or source p during time step h.
        /// for sources it is a negative value representing the 
        /// production rate on each time step (max possible production). 
        /// For each source it can take only two values: 0 
        /// (for maintenance days) or the production rate.</summary>
        /// 
        public double[] Forecast { get; set; }


        /// <summary> tank capacity in mass for customer or source p. 
        /// It is the maximum quantity of product that can be stored by 
        /// the customer or source, regardless of the minimum quantity 
        /// of product that must remain in the container and the part
        ///  of the container that must remain empty for pressure reasons.
        /// for sources it represents storage capacity (finite).</summary>
        /// 
        public double Capacity { get; set; }


        //// the tank quantity or stock expressed in mass for customer 
        /// or source p at the beginning of time step 0.</summary>
        /// 
        public double InitialTankQuantity { get; set; }

        /// <summary>
        /// The minimum quantity to be delivered for each operation at this customer.
        /// </summary>
        public double MinOperationQuantity { get; set; }


        /// <summary>The fix part of load/delivery time as far as the Point 
        /// (customer or source) is concerned (it is recommended to set this 
        /// value to an average or median time computed for this customer).</summary>
        /// 
        public int setupTime;


		/// <summary>Safety level in mass for Point p. this level is 
		/// the one that will be considered in the objective function 
		/// to size inventory shortages.</summary>
		/// 
        public double SafetyLevel { get; set; }


        /// <summary>The set of availability intervals of Point p, each included 
        /// in [0,T[. At most two per day. </summary>
        /// 
        public TimeWindow[] timewindows;  


        /// <summary>The set of trailers that are allowed to enter this site
        /// (for instance because of available equipments).</summary>
        /// 
        public int[] allowedTrailers;



		#endregion

		#region METHODS

        /// <summary>
        /// Default constructor.
        /// </summary>
        public IRP_Roadef_Challenge_Instance_Customers()
        {
         
           
        }


        /// <summary>
        /// Return the geoIndex of this point  
        public int getIndex()
        {
            return index;
        }

		#endregion
	}
}
