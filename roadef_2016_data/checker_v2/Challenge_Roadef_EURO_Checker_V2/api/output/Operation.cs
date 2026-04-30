using System;

namespace Roadef_Challenge.api.output
{
    /// <summary>A loading or delivery operation.</summary>
    /// 
    /// 
    [Serializable]
    public class Operation
    {
        #region FIELDS

        /// <summary>
        /// Unique identifier of the operation.</summary>
        /// 
        public int index;


        /// <summary>The index of the Point p where operation o takes place.</summary>
        /// 
        public int point;


        /// <summary>The quantity to be delivered (negative for sources) in operation o.</summary>
        /// 
        /// 
        public double Quantity { get; set; }


        /// <summary>The arrival time of operation o (in [0,T[).</summary>
        /// 
        public int arrival;



        /// <summary>The cumulated driving time between the last layover and operation o..</summary>
        /// 
        public int cumulatedDrivingTime;


        /// <summary>A departure time from point(o) after operation o(in [0,T[).</summary>
        /// 
        public int departure;


        /// <summary>The quantity of bulk in the trailer after performing this operation.</summary>
        /// 
        public double TrailerQuantity;


        /// <summary>layoverafter indicates whenever there is a layover after this operation
        /// 
        public int layoverbefore;


        /// <summary> driving time from the previous point in shift s o. It is equal to 0 if the layover is taken at the location of the previous operation o in shift s SHIFTS.
        /// It 	must be non-negative (≥ 0). 
        public int drivingtimebeforelayover;

        #endregion
    }
}