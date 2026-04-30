using System;

namespace Roadef_Challenge.api.input
{
	/// <summary>Time interval.</summary>
	/// 
    [Serializable]
	public class TimeWindow
	{
		#region FIELDS

		/// <summary>Start time of the interval (included).</summary>
		/// 
		public int start;


		/// <summary>End time of the interval (excluded).</summary>
		/// 
		public int end;

		#endregion

		#region METHODS

		/// <summary>We need a constructor without parameter in order to allow serialization.</summary>
		/// 
		public TimeWindow()
		{
		}


		/// <summary> We offer a constructor with natural parameters in order to simplify object creation.</summary>
		/// 
		public TimeWindow(int start, int end)
		{
			this.start = start;
			this.end = end;
		}


		/// <summary>Printer.</summary>
		/// 
		/// <returns>Time Window reprensation.</returns>
		/// 
		public override string ToString()
		{
			return "[" + start + "," + end + "]";
		}

		#endregion
	}
}