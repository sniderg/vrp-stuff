using System;
using System.Diagnostics;
using System.Xml.Serialization;
using Roadef_Challenge.api.input;
using Roadef_Challenge.util;
using System.IO;
namespace Roadef_Challenge.api.output
{
    /// <summary>
    /// A solution of is a set of shifts.</summary>
    /// 
    [XmlRoot("IRP_Roadef_Challenge_Output")]
    [Serializable]
    public class IRP_Roadef_Challenge_Output_
    {
        public IRP_Roadef_Challenge_Shift_[] Shifts { get; set; }

        public IRP_Roadef_Challenge_Output_()
        {

        }
    }
}

