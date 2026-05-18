using System;

namespace Roadef_Challenge.api.output
{
	/// <summary>Evolution of the quantity of bulk in the tank of the specified site.</summary>
	/// 
	/// 
    [Serializable]
	public class IRP_Roadef_Challenge_SiteInventory
	{
		#region FIELDS

		/// <summary>The index of the site.</summary>
		/// 
		public int site;


		/// <summary>Quantity of product in the tank at the end of each period.</summary>
		/// 
        public double[] TankQuantity { get; set; }


		#endregion

		#region METHODS

		/// <summary>Create an inventory for the given site, over the specified horizon.</summary>
		/// 
		/// <param name="site">The index of a site</param>
		/// <param name="horizon">The number of time steps (hence the length of the tankQuantity array to be allocated)</param>
		/// 
		public IRP_Roadef_Challenge_SiteInventory(int site, int horizon)
		{
			this.site = site;
            TankQuantity = new double[horizon];
		}

		/// <summary>Empty constructor.</summary>
		/// 
        public IRP_Roadef_Challenge_SiteInventory()
		{
		}

		#endregion
	}
}