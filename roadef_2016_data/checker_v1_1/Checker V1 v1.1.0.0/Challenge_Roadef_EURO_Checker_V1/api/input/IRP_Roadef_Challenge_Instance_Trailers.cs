using System;

namespace Roadef_Challenge.api.input
{
	/// <summary>Trailers are gas containers.</summary>
	/// 
    [Serializable]
    public class IRP_Roadef_Challenge_Instance_Trailers
	{
		
		#region FIELDS

        /// <summary> The unique index for this resource.</summary>
        /// 
        public int index;


		/// <summary>The capacity of this trailer in mass. That is to say the quantity 
		/// of product that can be loaded in the trailer and delivered to customersByRunoutDate,
		///  regardless of the minimum quantity of product that must remain in the container 
		/// and the part of the container that must remain empty for pressure reasons. 
		/// it is the usable capacity. </summary>
		/// 
        public double Capacity { get; set; }


		/// <summary>The mass of bulk in this trailer at the beginning of period [0,T[.
		///  Must bepublic int to [0, capacity].</summary>
		/// 
        public double InitialQuantity { get; set; }

        //public double TimeCost { get; set; }



        /// <summary>The cost per unit of distance.</summary>
        /// 
        public double DistanceCost { get; set; }



		#endregion

		#region METHODS

		

		#endregion
	}
}