using System;
using Roadef_Challenge.api.input;

namespace Roadef_Challenge.api.output
{
    /// <summary>A shift is a list of operations assigned to a vehicle.</summary>
    /// 
    [Serializable]
    public class IRP_Roadef_Challenge_Shift_
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

        /// <summary>The starting time for the this shift (in [0,T[).</summary>
        /// 
        public int start;

        public IRP_Roadef_Challenge_Operation_[] operations;


        #endregion

        #region METHODS



        #endregion

    }
}