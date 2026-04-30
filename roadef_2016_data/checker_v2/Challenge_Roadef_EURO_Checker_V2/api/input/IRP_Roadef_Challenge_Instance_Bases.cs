using System;

namespace Roadef_Challenge.api.input
{
	/// <summary>A base is a starting and ending  point for shifts.</summary>
	/// 
    [Serializable]
    public class IRP_Roadef_Challenge_Instance_Bases
	{
      #region FIELDS

		/// <summary> The unique index for this point. 
		/// This index is the index of the Point in the array that would 
		/// be obtained by concatenation of bases,sources and customers arrays.</summary>
		/// 
		public int index;


		#endregion

	  #region METHODS

		/// <summary>
		/// Return the geoIndex of this point  
		public  int getIndex()
        {
            return index;
        }

		#endregion

     }
}
