using System;
using Roadef_Challenge.api.input;

namespace Roadef_Challenge.api.output
{
    /// <summary>A shift is a list of operations assigned to a vehicle.</summary>
    /// 
    [Serializable]
    public class IRP_Roadef_Challenge_Shift
    {
        #region FIELDS

        /// <summary>The index of this shift in the shifts array in the output object.</summary>
        /// 
        public int index;


        /// <summary>The driver for this shift (identified by its index).</summary>
        /// 
        public int driver;

        /// <summary>The trailer for this shift(identified by its index).</summary>
        /// 
        public int trailer;


        /// <summary>The base of this shift(identified by its index).</summary>
        /// 
        //public int baseIndex;


        /// <summary>The starting time for the this shift (in [0,T[).</summary>
        /// 
        public int start;


        /// <summary>The departure time (in [0,T[) of this shift from its base.</summary>
        /// 
        //public int departure;


        /// <summary>Arrival time at the base at the end of the this shift (in [0,T[)</summary>
        /// 
        //public int arrival;


        /// <summary>Ending time for the shift (can differ by a few minutes from arrival(s)
        ///  because of checking tasks taking place at the base). In [0,T[.</summary>
        /// 
        public int end;


        /// <summary>The quantity of bulk in the trailer at the beginning of the this shift.</summary>
        /// 
        public double StartTrailerQuantity { get; set; }


        /// <summary>The quantity of bulk in the trailer at the end of the this shift.</summary>
        /// 
        public double EndTrailerQuantity { get; set; }

        /// <summary>List of operations</summary>
        /// 
        public Operation[] operations;

        /// <summary>Fix cost for this shift.</summary>
        /// 
        //public double FixCosts { get; set; }

        /// <summary>Distance costs for this shift</summary>
        /// 
        public double DistanceCosts { get; set; }

       
        /// <summary>Time costs for this shift.</summary>
        /// 
        public double TimeCosts { get; set; }

        /// <summary>Layover costs for this shift.</summary>
        /// 
        public double LayoverCosts { get; set; }


        #endregion

        #region METHODS

        /// <summary>Return the total cost of this shift (sum of all cost variables).</summary>		
        /// <returns>Total cost of this shift.</returns>
        /// 
        public double getCost()
        {
            return DistanceCosts + TimeCosts + LayoverCosts;
        }

        #endregion

    }
}