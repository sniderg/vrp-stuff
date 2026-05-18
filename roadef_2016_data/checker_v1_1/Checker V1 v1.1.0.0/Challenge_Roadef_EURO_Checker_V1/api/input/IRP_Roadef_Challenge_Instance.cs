using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Xml.Serialization;
using Roadef_Challenge.util;
using System.IO;
using System.Runtime.Serialization.Formatters.Binary;



namespace Roadef_Challenge.api.input
{
    /// <summary>This class describes all the input data for one IRP_Roadef_Challenge_Instance.</summary>
    /// 
	[XmlRoot("IRP_Roadef_Challenge_Instance")]
    [Serializable]
	public class IRP_Roadef_Challenge_Instance
    {

        #region FIELDS

		/// <summary>The name of the instance. </summary>
		/// 
		public String name;


		/// <summary>The duration of timesteps. This granularity is 
		/// the one of production/consumption forecasts. </summary>
		/// 
		public int unit;

		/// <summary>The horizon (constant H in the mathematical model) 
		/// gives the duration of the considered prevision period.
		/// 
		/// All time-related inputs will be defined as Point within 
		/// interval [0,horizon*unit[.</summary>
		/// 
		public int horizon;
        
	
		/// <summary>DISTMATRIX(p,q) is the distance between 
		/// Index p and q .</summary>
		/// 
        public double[][] DistMatrices { get; set; }

		/// <summary>TIMEMATRIX(p,q) is the travelling time 
		/// from p to q.</summary>
		/// 
		public int[][] timeMatrices;


        /// <summary>The list of drivers. </summary>
		/// 
        public IRP_Roadef_Challenge_Instance_driver[] drivers;

		/// <summary>The list of trailers.</summary>
		/// 
        public IRP_Roadef_Challenge_Instance_Trailers[] trailers;

		/// <summary>The list of bases.</summary>
		/// 
        public IRP_Roadef_Challenge_Instance_Bases bases; 

		/// <summary>The list of sources.</summary>
		/// 
        public IRP_Roadef_Challenge_Instance_Sources[] sources;

		/// <summary>The list of customers.</summary>
		/// 
        public IRP_Roadef_Challenge_Instance_Customers[] customers;
     

		#endregion

		#region METHODS

        public IRP_Roadef_Challenge_Instance()
        {
         
        }

   	
		/// <summary>Return the first minute outside of the schedule that is to say : (Horizon+1)*Unit.</summary>
		/// 
		/// <returns>The last Minute of the shedule</returns>
		/// 
		public int getLatestTime()
		{
			return ( horizon + 1 ) * unit;
		}


        #endregion 

       
   
	}
}
