using System;

namespace Roadef_Challenge.api.output
{
    /// <summary>A loading or delivery operation.</summary>
    /// 
    /// 
    [Serializable]
    public class IRP_Roadef_Challenge_Operation_
    {
        #region FIELDS

        /// <summary>The index of the Point p where operation o takes place.</summary>
        /// 
        public int point;


        /// <summary>The quantity to be delivered (negative for sources) in operation o.</summary>
        /// 
        public double Quantity { get; set; }


        /// <summary>The arrival time of operation o (in [0,T[).</summary>
        /// 
        public int arrival;


        #endregion
    }
}