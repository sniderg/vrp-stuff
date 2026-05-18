using System;
using System.Diagnostics;
using System.Xml.Serialization;
using Roadef_Challenge.api.input;
using Roadef_Challenge.util;
using System.IO;
namespace Roadef_Challenge.api.output
{
    /// <summary>
    /// A solution is a set of shifts.</summary>
    /// 
    [XmlRoot("IRP_Roadef_Challenge_Output")]
    [Serializable]
    public class IRP_Roadef_Challenge_Output
    {
        public IRP_Roadef_Challenge_Shift[] Shifts { get; set; }
        public IRP_Roadef_Challenge_SiteInventory[] Inventories { get; set; }
        public int NbLayovers { get; set; }
        public double TotalShiftsCosts { get; set; }
        public double LogisticRatios { get; set; }
        public double DeliveredQuantities { get; set; }


        public IRP_Roadef_Challenge_Output()
        {

        }

 
        /// <summary>
        /// Returns the output inventory for a site.</summary>
        /// 
        /// <param name="site">The site.</param>
        /// <param name="input">The input object.</param>
        /// <returns>The site inventory.</returns>
        /// 
        public IRP_Roadef_Challenge_SiteInventory getInventory(IRP_Roadef_Challenge_Instance_Customers site, IRP_Roadef_Challenge_Instance input)
        {
            Debug.Assert(site != null);
            IRP_Roadef_Challenge_SiteInventory siteInventory = Inventories[site.index - 1];
            Debug.Assert(siteInventory.site == site.index);
            return siteInventory;
        }


    }
}