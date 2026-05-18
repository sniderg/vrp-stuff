using System;

namespace Roadef_Challenge.api.input
{
	/// <summary>Represents a driver with its characteristics. 
	/// It can also represent a pair of drivers.</summary>
	/// 
    [Serializable]
    public class IRP_Roadef_Challenge_Instance_driver
	{
		#region FIELDS

        /// <summary> The unique index for this resource.</summary>
        /// 
        public int index;

	
        /// <summary>
        ///  The minimum duration between two consecutive shifts assigned to a driver d. </summary>
        public int minInterSHIFTDURATION;

		/// <summary>The maximum driving duration for this driver, 
		/// before getting a layover (e.g. 11 hours in the US).</summary>
		/// 
		public int maxDrivingDuration;


        public double TimeCost { get; set; }


        /// <summary>The set of availability intervals of this resource, 
        /// each included in [0,T[. These intervals are not allowed to overlap.</summary>
        /// 
        public TimeWindow[] timewindows;

        /// <summary>The list of tractors that can be driven by this driver.</summary>
        /// 
        public int trailer;


       

		#endregion

		#region METHODS

		

        #endregion
    }
}