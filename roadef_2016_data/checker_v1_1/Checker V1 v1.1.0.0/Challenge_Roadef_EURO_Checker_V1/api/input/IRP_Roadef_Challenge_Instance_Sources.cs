using System;

namespace Roadef_Challenge.api.input
{
	/// <summary>A source is a production site.</summary>
	/// 
    [Serializable]
    public class IRP_Roadef_Challenge_Instance_Sources
	{
        #region FIELDS

        /// <summary> The unique index for this point. 
        /// This index is the index of the Point in the array that would 
        /// be obtained by concatenation of bases,sources and customers arrays.</summary>
        /// 
        public int index;

      

        /// <summary>The fix part of load/delivery time as far as the Point 
        /// (customer or source) is concerned (it is recommended to set this 
        /// value to an average or median time computed for this customer).</summary>
        /// 
        public int setupTime;

        #endregion


		#region METHODS

        /// <summary>
        /// Return the geoIndex of this point  
        public int getIndex()
        {
            return index;
        }
		
		#endregion
	}
}
