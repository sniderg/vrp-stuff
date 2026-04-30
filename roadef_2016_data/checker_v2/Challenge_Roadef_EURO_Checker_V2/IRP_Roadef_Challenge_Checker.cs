using System;
using System.Diagnostics;
using System.IO;
using System.Xml.Serialization;
using Roadef_Challenge.api.input;
using Roadef_Challenge.api.output;
using Roadef_Challenge.util;

namespace Roadef_Challenge.checker
{
    /// <summary>
    /// Checks an Output file to detect non coherent results.</summary>
    /// 
    [XmlRoot("IRP_Roadef_Challenge_Checker")]
    [Serializable]
    public class IRP_Roadef_Challenge_Checker
    {

        #region Fields

        /// <summary>
        /// Input file related to this output file.</summary>
        /// 
        internal IRP_Roadef_Challenge_Instance input;

        /// <summary>
        /// Output file to check.</summary>
        /// 
        public IRP_Roadef_Challenge_Output output;


        /// <summary>
        /// Input File name associated to this output file to check.</summary>
        /// 
        internal String inputFilename;

        /// <summary>
        /// Input File name associated to this output file to check.</summary>
        /// 
        internal String instanceName;

        /// <summary>
        /// Output File name of an output data to check.</summary>
        /// 
        internal String outputFilename;


        /// <summary>
        /// The number of minutes for planning.</summary>
        /// 
        internal int NbMinutesRunoutsHorizon { get { return input.horizon * input.unit; } }

        /// <summary>
        /// The number of minutes for planning.</summary>
        /// 
        internal int NbMinutesMissedOrdersHorizon { get { return input.horizon * input.unit; } }

        #endregion


        #region Methods

        /// <summary>
        /// Check all data structures from an input files.</summary>
        /// 
        /// <param name="inputFilename">Input File name associated to this output file to check.</param>
        /// <param name="outputFilename">Output File name of an output data to check.</param>
        /// 
        public IRP_Roadef_Challenge_Checker(String inputFilename, String outputFilename)
        {
            this.inputFilename = inputFilename;
            this.outputFilename = outputFilename;
            this.instanceName = inputFilename;
        }

        public IRP_Roadef_Challenge_Checker()
        {

        }


        /// <summary>
        /// Check all data structures from an IRP_Roadef_Challenge_Output.</summary>
        /// 

        public IRP_Roadef_Challenge_Checker(IRP_Roadef_Challenge_Instance Input, IRP_Roadef_Challenge_Output Output)
        {
            input = Input;
            output = Output;
        }


        /// <summary>
        /// Check all data structures from an IRP_Roadef_Challenge_Output.</summary>
        ///
        public IRP_Roadef_Challenge_Checker(IRP_Roadef_Challenge_Instance Input, IRP_Roadef_Challenge_Output_ Output)
        {
            input = Input;
            this.output = new IRP_Roadef_Challenge_Output();
            this.output.Shifts = new IRP_Roadef_Challenge_Shift[Output.Shifts.Length];

            #region classification of shifts per trailers
            int[] number_of_shifts_performed_by_trailer = new int[input.trailers.Length];
            foreach (IRP_Roadef_Challenge_Shift_ sh in Output.Shifts)
            {
                number_of_shifts_performed_by_trailer[sh.trailer]++;
            }

            int[][] shifts_performed_by_trailers;
            shifts_performed_by_trailers = new int[Input.trailers.Length][];

            for (int tl = 0; tl < Input.trailers.Length; tl++)
            {
                shifts_performed_by_trailers[tl] = new int[number_of_shifts_performed_by_trailer[tl]];
            }

            shifts_performed_by_trailers = shifts_performed_by_each_trailer(Output.Shifts);

            #endregion


            #region computation of intermediate variables of shifts
            //instanciation of shift
            for (int tl = 0; tl < Input.trailers.Length; tl++)
            {
                for (int sh = 0; sh < shifts_performed_by_trailers[tl].Length; sh++)
                {
                    int SH = shifts_performed_by_trailers[tl][sh];

                    this.output.Shifts[SH] = new IRP_Roadef_Challenge_Shift();
                    this.output.Shifts[SH].operations = new Operation[Output.Shifts[SH].operations.Length + 1];
                    for (int o = 0; o < this.output.Shifts[SH].operations.Length; o++)
                    {
                        this.output.Shifts[SH].operations[o] = new Operation();
                    }
                }
            }

            int numberOfLayover = 0;
            for (int tl = 0; tl < Input.trailers.Length; tl++)
            {
                if(shifts_performed_by_trailers[tl].Length > 0)
                {
                    this.output.Shifts[shifts_performed_by_trailers[tl][0]].StartTrailerQuantity = Input.trailers[tl].InitialQuantity;

                    for (int sh = 0; sh < shifts_performed_by_trailers[tl].Length; sh++)
                    {

                        int SH = shifts_performed_by_trailers[tl][sh];


                        // this.output.Shifts[SH] = new IRP_Roadef_Challenge_Shift();
                        this.output.Shifts[SH].index = Output.Shifts[SH].index;
                        this.output.Shifts[SH].driver = Output.Shifts[SH].driver;
                        this.output.Shifts[SH].trailer = Output.Shifts[SH].trailer;
                        this.output.Shifts[SH].start = Output.Shifts[SH].start;


                        for (int o = 0; o < this.output.Shifts[SH].operations.Length - 1; o++)
                        {
                            this.output.Shifts[SH].operations[o].index = o;
                            this.output.Shifts[SH].operations[o].point = Output.Shifts[SH].operations[o].point;
                            this.output.Shifts[SH].operations[o].arrival = Output.Shifts[SH].operations[o].arrival;
                            this.output.Shifts[SH].operations[o].Quantity = Output.Shifts[SH].operations[o].Quantity;
                        }


                        #region *************** Last  operation
                        this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].index = this.output.Shifts[SH].operations.Length - 1;
                        this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].point = 0;
                        this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].Quantity = 0;


                        for (int o = 0; o < this.output.Shifts[SH].operations.Length; o++)
                        {
                            if (this.output.Shifts[SH].operations[o].point == 0)
                            {
                                //problem arrival at the depot
                                this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].arrival = this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 2].departure + Input.timeMatrices[this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 2].point][0];

                                this.output.Shifts[SH].operations[o].departure = this.output.Shifts[SH].operations[o].arrival;
                            }
                            else
                            {
                                if (this.output.Shifts[SH].operations[o].point < Input.sources.Length + 1)
                                    this.output.Shifts[SH].operations[o].departure = this.output.Shifts[SH].operations[o].arrival + Input.sources[this.output.Shifts[SH].operations[o].point - 1].setupTime;
                                else
                                    this.output.Shifts[SH].operations[o].departure = this.output.Shifts[SH].operations[o].arrival + Input.customers[this.output.Shifts[SH].operations[o].point - (Input.sources.Length + 1)].setupTime;
                            }
                        }

                        #endregion


                        #region******************* find Layovers in the shift

                        
                        if (this.output.Shifts[SH].operations[0].arrival - this.output.Shifts[SH].start >= Input.drivers[this.output.Shifts[SH].driver].LayoverDuration + Input.timeMatrices[0][this.output.Shifts[SH].operations[0].point])
                        {
                            this.output.Shifts[SH].operations[0].layoverbefore = 1;
                            numberOfLayover++;
                        }
                        else
                        {
                            this.output.Shifts[SH].operations[0].layoverbefore = 0;
                        }

                        for (int o = 1; o < this.output.Shifts[SH].operations.Length; o++)
                        {
                            if (this.output.Shifts[SH].operations[o].arrival - this.output.Shifts[SH].operations[o - 1].departure >= Input.drivers[this.output.Shifts[SH].driver].LayoverDuration + Input.timeMatrices[this.output.Shifts[SH].operations[o-1].point][this.output.Shifts[SH].operations[o].point])
                            {
                                this.output.Shifts[SH].operations[o].layoverbefore = 1;
                                numberOfLayover++;
                            }
                            else
                            {
                                this.output.Shifts[SH].operations[o].layoverbefore = 0;
                            }
                        }

                        #endregion


                        #region ******************* Cumulated driving time

                        if (this.output.Shifts[SH].operations[0].layoverbefore == 1)
                        {
                            this.output.Shifts[SH].operations[0].drivingtimebeforelayover = Math.Min(Input.drivers[this.output.Shifts[SH].driver].maxDrivingDuration , Input.timeMatrices[0][this.output.Shifts[SH].operations[0].point]);
                            this.output.Shifts[SH].operations[0].cumulatedDrivingTime = Input.timeMatrices[0][this.output.Shifts[SH].operations[0].point] - this.output.Shifts[SH].operations[0].drivingtimebeforelayover; //to complete !!!!!!
                        }
                        else
                        {
                            this.output.Shifts[SH].operations[0].cumulatedDrivingTime = Input.timeMatrices[0][this.output.Shifts[SH].operations[0].point];
                        }

                        for (int o = 1; o < this.output.Shifts[SH].operations.Length; o++)
                        {
                            if (this.output.Shifts[SH].operations[o].layoverbefore == 1)
                            {
                                this.output.Shifts[SH].operations[o].drivingtimebeforelayover = Math.Min(Input.drivers[this.output.Shifts[SH].driver].maxDrivingDuration - this.output.Shifts[SH].operations[o - 1].cumulatedDrivingTime, Input.timeMatrices[this.output.Shifts[SH].operations[o - 1].point][this.output.Shifts[SH].operations[o].point]);
                                this.output.Shifts[SH].operations[o].cumulatedDrivingTime = Input.timeMatrices[this.output.Shifts[SH].operations[o - 1].point][this.output.Shifts[SH].operations[o].point] - this.output.Shifts[SH].operations[o].drivingtimebeforelayover; //to complete !!!!!!
                            }
                            else
                            {
                                //if (o < this.output.Shifts[SH].operations.Length - 1)
                                //{                                  
                                    this.output.Shifts[SH].operations[o].cumulatedDrivingTime = this.output.Shifts[SH].operations[o-1].cumulatedDrivingTime + Input.timeMatrices[this.output.Shifts[SH].operations[o - 1].point][this.output.Shifts[SH].operations[o].point]; //to complete !!!!!!
                               // }
                               // else
                               // {
                               //     this.output.Shifts[SH].operations[o].cumulatedDrivingTime = this.output.Shifts[SH].operations[o - 1].cumulatedDrivingTime + Input.timeMatrices[this.output.Shifts[SH].operations[o - 1].point][0]; //to complete !!!!!!                               
                               // }                               
                            }

                            //this.output.Shifts[SH].operations[o].cumulatedDrivingTime = this.output.Shifts[SH].operations[o - 1].cumulatedDrivingTime + Input.timeMatrices[this.output.Shifts[SH].operations[o - 1].point][this.output.Shifts[SH].operations[o].point];                                               
                        }



                        bool presenceOfLayoverBeforeLastOperation = false;
                        if (this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 2].cumulatedDrivingTime + Input.timeMatrices[this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 2].point][0] > Input.drivers[this.output.Shifts[SH].driver].maxDrivingDuration)
                        {
                            foreach (Operation op in this.output.Shifts[SH].operations)
                            {
                                if (op.layoverbefore == 1)
                                {
                                    presenceOfLayoverBeforeLastOperation = true;
                                }
                            }

                            if (!presenceOfLayoverBeforeLastOperation)
                            {
                                this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].layoverbefore = 1;
                                numberOfLayover++;

                                this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].arrival = this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 2].departure + Input.timeMatrices[this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 2].point][0] + Input.drivers[this.output.Shifts[SH].driver].LayoverDuration;

                                this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].departure = this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].arrival;


                                this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].drivingtimebeforelayover = Math.Min(Input.drivers[this.output.Shifts[SH].driver].maxDrivingDuration - this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 2].cumulatedDrivingTime, Input.timeMatrices[this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 2].point][this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].point]);
                                this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].cumulatedDrivingTime = Input.timeMatrices[this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 2].point][this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].point] - this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].drivingtimebeforelayover; //to complete !!!!!!


                            }
                        }

                        #endregion

                        this.output.Shifts[SH].end = this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].arrival;


                        if (sh > 0)
                        {
                            this.output.Shifts[SH].StartTrailerQuantity = this.output.Shifts[shifts_performed_by_trailers[tl][sh - 1]].operations[this.output.Shifts[shifts_performed_by_trailers[tl][sh - 1]].operations.Length - 1].TrailerQuantity;
                            this.output.Shifts[SH].operations[0].TrailerQuantity = this.output.Shifts[SH].StartTrailerQuantity - this.output.Shifts[SH].operations[0].Quantity;
                        }
                        else
                        {
                            this.output.Shifts[shifts_performed_by_trailers[tl][0]].operations[0].TrailerQuantity = Input.trailers[tl].InitialQuantity - this.output.Shifts[shifts_performed_by_trailers[tl][0]].operations[0].Quantity;
                        }


                        

                        double cumulatedDist = Input.DistMatrices[0][this.output.Shifts[SH].operations[0].point];

                        for (int o = 1; o < this.output.Shifts[SH].operations.Length; o++)
                        {
                            this.output.Shifts[SH].operations[o].TrailerQuantity = this.output.Shifts[SH].operations[o - 1].TrailerQuantity - this.output.Shifts[SH].operations[o].Quantity;
                            cumulatedDist = cumulatedDist + Input.DistMatrices[this.output.Shifts[SH].operations[o - 1].point][this.output.Shifts[SH].operations[o].point];
                        }

                        this.output.Shifts[SH].EndTrailerQuantity = this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].TrailerQuantity;

                       // cumulatedDist = cumulatedDist + Input.DistMatrices[this.output.Shifts[SH].operations[this.output.Shifts[SH].operations.Length - 1].point][0];

                        this.output.Shifts[SH].DistanceCosts = cumulatedDist * Input.trailers[this.output.Shifts[SH].trailer].DistanceCost;


                        int WorkingTime = this.output.Shifts[SH].end - this.output.Shifts[SH].start;

                        int nblayover =0;
                        foreach (Operation operation in this.output.Shifts[SH].operations)
                        {
                            if (operation.layoverbefore == 1)
                            {
                                nblayover++;
                            }
                        }

                        WorkingTime = WorkingTime - nblayover * input.drivers[this.output.Shifts[SH].driver].LayoverDuration;

                        this.output.Shifts[SH].TimeCosts = WorkingTime * Input.drivers[this.output.Shifts[SH].driver].TimeCost;

                        this.output.Shifts[SH].LayoverCosts = nblayover * input.drivers[this.output.Shifts[SH].driver].LayoverCost;
                                               
                    }

                }

            }
            #endregion


            #region customer inventory profil

            this.output.Inventories = new IRP_Roadef_Challenge_SiteInventory[input.sources.Length + input.customers.Length + 1];
            double[][] operationQuantities = new double[input.sources.Length + input.customers.Length + 1][];
            for (int site = input.sources.Length + 1; site < input.sources.Length + input.customers.Length + 1; site++)
            {
                operationQuantities[site] = new double[Input.horizon];
            }

            int indexShift = 0;
            foreach (IRP_Roadef_Challenge_Shift_ shift in Output.Shifts)
            {
                int indexOperation = 0;

                foreach (IRP_Roadef_Challenge_Operation_ operation in shift.operations)
                {
                    if (indexOperation < shift.operations.Length && operation.point > Input.sources.Length)
                    {
                        int operationTS = operation.arrival / input.unit;

                        operationQuantities[operation.point][operationTS] += operation.Quantity;
                    }
                    indexOperation++;
                }
                indexShift++;
            }
            int a = 1;
            a = a + 1;
            for (int site = input.sources.Length + 1; site < input.sources.Length + input.customers.Length + 1; site++)
            {
                this.output.Inventories[site] = new IRP_Roadef_Challenge_SiteInventory();

                double curLevel = Input.customers[site - (input.sources.Length + 1)].InitialTankQuantity;
                this.output.Inventories[site].TankQuantity = new double[Input.horizon];
                for (int i = 0; i < Input.horizon; i++)
                {
                    curLevel = curLevel - Input.customers[site - (input.sources.Length + 1)].Forecast[i] + operationQuantities[Input.customers[site - (input.sources.Length + 1)].index][i];
                    this.output.Inventories[site].TankQuantity[i] = curLevel;
                    this.output.Inventories[site].site = site;
                }
            }

            a = a + 1;
            #endregion


            #region
            //this.output.TotalShiftsCosts = output.TotalShiftsCosts[output.TotalShiftsCosts.Length-1];
            //this.output.LogisticRatios = output.LogisticRatios[output.LogisticRatios.Length - 1];
            //this.output.DeliveredQuantities = output.DeliveredQuantities[output.DeliveredQuantities.Length - 1];

            var planningHorizon = input.horizon;
            var nbMinutesPlanningHorizon = planningHorizon * input.unit;

            double shiftCosts = 0.0d;
            var deliveredQuantity = 0.0d;

            foreach (IRP_Roadef_Challenge_Shift shift in this.output.Shifts)
            {
                if (shift.start >= nbMinutesPlanningHorizon) continue;

                shiftCosts += shift.getCost();

                foreach (Operation operation in shift.operations)
                {
                    int customer = operation.point;

                    if (customer < input.customers.Length + input.sources.Length + 1 && customer >= input.sources.Length + 1)
                    {
                        deliveredQuantity += operation.Quantity;
                    }
                }
            }

            this.output.TotalShiftsCosts = shiftCosts;
            this.output.DeliveredQuantities = deliveredQuantity;

            double logisticRatio = 0.0d;
            if (Floating.StrictlyGreater(deliveredQuantity, 0))
            {
                logisticRatio = shiftCosts / deliveredQuantity;
                this.output.LogisticRatios = logisticRatio;
            }

            this.output.NbLayovers = numberOfLayover;
          
            

            #endregion
        }


        /// <summary>
        /// Performs a complete check of all data structures.</summary>
        /// 
        /// <return>True if well-formed.</return>
        /// 
        public bool checkAllOutputData()
        {
            bool value;

            if (input == null)
            {
                Console.WriteLine("[ checkAllOutputData ] : inputFile null.");
                value = false;
            }
            else
            {
                if (output == null)
                {
                    Console.WriteLine("[ checkAllOutputData ] : outputFile null.");
                    value = false;
                }
                else
                {
                    //Console.WriteLine( "[ checkAllOutputData ] : checkShifts." );
                    value = checkLayovers();

                    //Console.WriteLine( "[ checkAllOutputData ] : checkShifts." );
                    value = value & checkShifts();

                    //Console.WriteLine( "[ checkAllOutputData ] : checkSites." );
                    value = value & checkSites();

                    //Console.WriteLine( "[ checkAllOutputData ] : checkResources." );
                    value = value & checkResources();

                    //Console.WriteLine( "[ checkAllOutputData ] : checkServiceQuality." );
                    value = value & checkServiceQuality();

                    //Console.WriteLine( "[ checkAllOutputData ] : checkCosts." );
                    value = value & checkCosts();
                }
            }

            return value;
        }



        #region Checkers on Layovers Constraints

        /// <summary>
        /// For each shifts with layover of the output file, check all constraints related to layover.</summary>
        /// 
        /// <returns>True if all shifts are OK.</returns>
        /// 
        internal bool checkLayovers()
        {
            bool value = true;

            int indexShift = 0;

            foreach (IRP_Roadef_Challenge_Shift shift in output.Shifts)
            {
                //Console.WriteLine( "*********** [ checkShifts ] : check Shift[" + indexShift + "] ***********" );

                if (shift == null)
                {
                    Console.WriteLine("[ checkLayovers ] : shift null in shifts at index " + indexShift + ".");
                    value = false;
                }
                else
                {

                    IRP_Roadef_Challenge_Instance_driver shiftDriver = null;
                    if (!getDriver(shift, ref shiftDriver)) return false;

                    IRP_Roadef_Challenge_Instance_Trailers shiftTrailer = null;
                    if (!getTrailer(shift, ref shiftTrailer)) return false;                  

                    value &= checkLAY02(shift, indexShift);

                    value &= checkLAY03(shift, indexShift);

                }

                indexShift++;
            }

            return value;
        }

        #region Subcheckers on Layovers Constraints

        /// <summary>
        /// [ LAY02 : shift must include a Layover if there is one or more deliveries to layover customers 
        /// </summary>
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param>
        /// LAY02 are OK.</returns>
        /// 
        internal bool checkLAY02(IRP_Roadef_Challenge_Shift shift, int indexShift)
        {
            bool value = true;

            //Console.WriteLine( "[LAY02] on " + shiftName );
            bool LayoverOK = false;
            foreach (Operation operation in shift.operations)
            {
                if (operation.layoverbefore == 1)
                {
                    LayoverOK = true;
                }
            }
            if (LayoverOK)
            {
                value = false;
                foreach (Operation operation in shift.operations)
                {
                    if (operation.point >= input.sources.Length + 1)
                    {
                        if (input.customers[operation.point - (input.sources.Length + 1)].LayoverCustomer==1)
                        {
                            value = true;
                        }
                    }
                }

            }

            if (!value)
                {
                    Console.WriteLine("[ LAY02 : checkLayovers ] : shift " + indexShift + " contains a layover without layover customer.");
                }
               
            return value;
        }


        /// <summary>
        /// [ LAY03 : Only one layover per shift is allowed ].</summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param> 
        /// 
        /// <returns>True if SHI03 are OK.</returns>
        /// 
        internal bool checkLAY03(IRP_Roadef_Challenge_Shift shift, int indexShift)
        {
            bool value = true;

            //Console.WriteLine( "[LAY03] on " + shiftName );

            int NbreLayovers = 0;

            foreach (Operation operation in shift.operations)
            {
                if (operation.layoverbefore == 1)
                {
                    NbreLayovers++; 
                }
            }


            if (NbreLayovers > 1)
            {
                Console.WriteLine("[ LAY03 : checkLayovers ] : shift " + indexShift + " contains more than one  layover.");
                value= false;
            }

            return value;
        }

        #endregion

        #endregion


        #region Checkers on Shifts Constraints

        /// <summary>
        /// For each shifts of the output file, check all constraints.</summary>
        /// 
        /// <returns>True if all shifts are OK.</returns>
        /// 
        internal bool checkShifts()
        {
            bool value = true;

            int indexShift = 0;

            foreach (IRP_Roadef_Challenge_Shift shift in output.Shifts)
            {
                //Console.WriteLine( "*********** [ checkShifts ] : check Shift[" + indexShift + "] ***********" );

                if (shift == null)
                {
                    Console.WriteLine("[ checkShifts ] : shift null in shifts at index " + indexShift + ".");
                    value = false;
                }
                else
                {
                    IRP_Roadef_Challenge_Instance_driver shiftDriver = null;
                    if (!getDriver(shift, ref shiftDriver)) return false;

                    IRP_Roadef_Challenge_Instance_Trailers shiftTrailer = null;
                    if (!getTrailer(shift, ref shiftTrailer)) return false;

                    value &= checkSHI02(shift, indexShift, shiftDriver);

                    value &= checkSHI03(shift, indexShift);

                    value &= checkSHI04(shift, indexShift);

                    value &= checkSHI05(shift, indexShift , shiftTrailer);

                    value &= checkSHI06SHI07();

                    value &= checkSHI11(shift, indexShift);

                    value &= checkSHI16(shift, indexShift);

                }

                indexShift++;
            }

            //Console.WriteLine( "*********** [ checkShifts ] : trailerQuantities between shifts ***********" );

            value &= checkSHI06SHI07();

            return value;
        }

        #region Subcheckers on Shifts Constraints

        /// <summary>
        /// [ SHI02 : Arrival at a point requires traveling from the previous point to this point ]
        /// Notes that we use inequalities in order to allow waiting time between the end of 
        /// travel and arrival(o) which represents the actual entry in the site (that can be 
        /// delayed because of opening hours).</summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param>
        /// 
        /// <returns>True if SHI02 are OK.</returns>
        /// 
        internal bool checkSHI02(IRP_Roadef_Challenge_Shift shift, int indexShift, IRP_Roadef_Challenge_Instance_driver shiftDriver)
        {
            bool value = true;

            //Console.WriteLine( "[SHI02] on " + shiftName );

            int lastPoint = 0;
            int lastDeparture = shift.start;
            foreach (Operation operation in shift.operations)
            {
                int currentPoint = operation.point;
                if (operation.arrival <
                    lastDeparture +
                    input.timeMatrices[lastPoint][currentPoint] + operation.layoverbefore * input.drivers[shift.driver].LayoverDuration)
                {
                    Console.WriteLine("[ SHI02 : checkShifts ] : 'arrival' at point[" + operation.point + "] in shift[" + indexShift +
                                      "] occurs too early : "
                                      + operation.arrival + " (arrival) < " + lastDeparture + " (departure) + "
                                      +
                                      input.timeMatrices[lastPoint][currentPoint] +
                                      " (travelTime)"
                                      + operation.layoverbefore * input.drivers[shift.driver].LayoverDuration+
                                      " (layover duration). "
                                      );
                    value = false;
                }
                lastPoint = currentPoint;
                lastDeparture = operation.departure;
            }

            return value;
        }


        /// <summary>
        /// [ SHI03 : Loading and delivery operations take a constant time ].</summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param> 
        /// 
        /// <returns>True if SHI03 are OK.</returns>
        /// 
        internal bool checkSHI03(IRP_Roadef_Challenge_Shift shift, int indexShift)
        {
            bool value = true;

            //Console.WriteLine( "[SHI03] on " + shiftName );

            int indexOperation = 0;

            foreach (Operation operation in shift.operations)
            {
                // All Operations but last one.
                if (indexOperation < shift.operations.Length - 1)
                {
                    if (operation.point < 0 || operation.point >= 1 + input.sources.Length + input.customers.Length)
                    {
                        Console.WriteLine("[ SHI03 : checkShifts ] : operation[" + indexOperation + "] of shift["
                                          + indexShift + "] has a wrong point index.");
                        return false;
                    }

                    int point = operation.point;

                    int setuptime = 0;

                    if (point > 0)
                    {
                        if (point < input.sources.Length + 1)

                            setuptime = input.sources[point - 1].setupTime;
                        else
                            setuptime = input.customers[point - (input.sources.Length + 1)].setupTime;


                        if (point < 0 && point > input.customers.Length + input.customers.Length + 1)
                        {
                            Console.WriteLine("[ SHI03 : checkShifts ] : operation["
                                              + indexOperation + "] of shift["
                                              + indexShift + "] not on a site.");
                            return false;
                        }

                        if (operation.departure < operation.arrival + setuptime)
                        {
                            Console.WriteLine("[ SHI03 : checkShifts ] : 'departure' of operation["
                                              + indexOperation + "] of shift[" + indexShift + "] occurs too early : "
                                              + operation.departure + " (departure) < " + operation.arrival + " (arrival) + " + setuptime +
                                              " (setupTime).");
                            value = false;
                        }

                    }
                }
                indexOperation++;
            }

            return value;
        }

        /// <summary>
        /// [ SHI04 : delivery operations are performed 
        /// during opening hours customers ] : 
        /// For all Operations, the interval [arrival(o),departure(o)] must 
        /// be fully included in one of the opening time-windows of the site.</summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param> 
        /// 
        /// <returns>True if SHI04 are OK.</returns>
        /// 
        internal bool checkSHI04(IRP_Roadef_Challenge_Shift shift, int indexShift)
        {
            bool value = true;

            //Console.WriteLine( "[SHI04] on " + shiftName );

            int indexOperation = 0;

            foreach (Operation operation in shift.operations)
            {
                // All Operations but not the last one.
                if (indexOperation < shift.operations.Length - 1)
                {
                    // Controls already perform on operationSite.

                    int site = operation.point;

                    if (site < 0 || site>=1+input.sources.Length+input.customers.Length)
                    {
                        Console.WriteLine("[ SHI04 : checkShifts ] : operation[" + indexOperation + "] of shift["
                                          + indexShift + "] not on a site.");
                        return false;
                    }

                    if (site >= 1 + input.sources.Length)
                    {
                        bool twFound = false;

                        int indTw = 0;

                        while (indTw < input.customers[site - ( 1 + input.sources.Length)].timewindows.Length && !twFound)
                        {
                            TimeWindow tw = input.customers[site - (1 + input.sources.Length)].timewindows[indTw];
                            if (tw.start <= operation.arrival && tw.end >= operation.departure) twFound = true;
                            indTw++;
                        }

                        if (!twFound)
                        {
                            Console.WriteLine("[ SHI04 : checkShifts ] : operation[" + indexOperation + "] of shift["
                                              + indexShift + "] is out of the"
                                              + " timewindows of site[" + site + "] ==> " + operation.arrival + " (operationStart) -> "
                                              + operation.departure + " (operationEnd).");
                            value = false;
                        }
                    }
                }
                indexOperation++;
            }

            return value;
        }



        /// <summary>
        /// [ SHI05 : Loading and delivery operations require 
        /// the site to be accessible for the vehicle ] : 
        /// The drivers must be allowed on this site.</summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param> 
        /// <param name="shiftTrailer">Trailer of the Shift.</param>
        /// 
        /// <returns>True if SHI05 are OK.</returns>
        /// 
        internal bool checkSHI05(IRP_Roadef_Challenge_Shift shift, int indexShift, IRP_Roadef_Challenge_Instance_Trailers shiftTrailer)
        {
            bool value = true;

            //Console.WriteLine( "[SHI05] on " + shiftName );

            int indexOperation = 0;

            foreach (Operation operation in shift.operations)
            {
                // All Operations but last one.
                if (indexOperation < shift.operations.Length - 1)
                {
                    // Controls already perform on operationSite.

                    int site = operation.point;

                    if (site < 0 || site>input.sources.Length+input.customers.Length+1)
                    {
                        Console.WriteLine("[ SHI05 : checkShifts ] : operation[" + indexOperation + "] of shift["
                                          + indexShift + "] not on a site.");
                        return false;
                    }


                    int indTrailer = 0;
                    bool trailFound = false;

                    if (site < input.sources.Length + input.customers.Length + 1 && site >= input.sources.Length + 1)
                    {
                        while (indTrailer < input.customers[site - (input.sources.Length+1)].allowedTrailers.Length && !trailFound)
                        {
                            if (input.customers[site - (input.sources.Length+1)].allowedTrailers[indTrailer] == shiftTrailer.index) trailFound = true;
                            indTrailer++;
                        }

                        if (!trailFound)
                        {
                            Console.WriteLine("[ SHI05 : checkShifts ] : operation[" + indexOperation + "] of shift[" + indexShift +
                                              "] can't accept"
                                              + " this trailer ==> trailer[" + shiftTrailer.index + "].");
                            value = false;

                        }
                    }



                    if (site < input.sources.Length + 1 && site > 0)
                    {
                        while (indTrailer < input.sources[site - 1].allowedTrailers.Length && !trailFound)
                        {
                            if (input.sources[site -  1].allowedTrailers[indTrailer] == shiftTrailer.index) trailFound = true;
                            indTrailer++;
                        }

                        if (!trailFound)
                        {
                            Console.WriteLine("[ SHI05 : checkShifts ] : operation[" + indexOperation + "] of shift[" + indexShift +
                                              "] can't accept"
                                              + " this trailer ==> trailer[" + shiftTrailer.index + "].");
                            value = false;

                        }
                    }


                }
                indexOperation++;
            }

            return value;
        }




        /// <summary>
        /// [ SHI06 : The trailerQuantity cannot be negative 
        /// or exceed capacity of the trailer ].
        /// 
        /// [ SHI07 : The initial quantity of a trailer on a shift
        /// is the end quantity on the previous shift of the trailer ].</summary> 
        /// 
        /// <returns>True if SHI06 and SHI07 are OK.</returns>
        /// 
        internal bool checkSHI06SHI07()
        {
            if (output == null) return false;

            bool value = true;

            // Initialize lastTrailerQuantity for each trailer.

            double[] lastTrailerQuantity = new double[input.trailers.Length];

            foreach (IRP_Roadef_Challenge_Instance_Trailers trailer in input.trailers)
            {
                lastTrailerQuantity[trailer.index] = trailer.InitialQuantity;
            }

            int indexShift = 0;

            foreach (IRP_Roadef_Challenge_Shift shift in output.Shifts)
            {
                IRP_Roadef_Challenge_Instance_Trailers shiftTrailer = null;

                if (!getTrailer(shift, ref shiftTrailer)) return false;

                #region SHI06

                //Console.WriteLine( "[SHI06] on " + shiftName );


                double lastQuantity = shift.StartTrailerQuantity;

                foreach (Operation operation in shift.operations)
                {
                    double quantity = operation.TrailerQuantity;
                    if (Floating.StrictlyGreater(0, quantity))
                    {
                        Console.WriteLine("[ SHI06 : checkShifts ] : Positive or Null value expected for 'trailerQuantity' at "
                                          + "point[" + operation.point + "] in shift[" + indexShift + "].");
                        value = false;
                    }
                    if (Floating.StrictlyGreater(quantity, shiftTrailer.Capacity))
                    {
                        Console.WriteLine("[ SHI06 : checkShifts ] : 'TrailerQuantity' should be under capacity at "
                                          + "point[" + operation.point + "] in shift[" + indexShift + "] => " + quantity +
                                          " (trailerQuantity) > "
                                          + shiftTrailer.Capacity + " (capacity).");
                        value = false;
                    }
                    if (!Floating.Equal(quantity, lastQuantity - operation.Quantity))
                    {
                        Console.WriteLine("[ SHI06 : checkShifts ] : 'TrailerQuantity' at point[" + operation.point
                                          + "] in shift[" + indexShift + "] non coherent with operation : "
                                          + quantity + " (trailerQuantity) != " + lastQuantity + " (lastQuantity) - "
                                          + operation.Quantity + " (operationQuantity).");
                        value = false;
                    }
                    lastQuantity = quantity;
                }

                #endregion


                #region SHI07

                //Console.WriteLine( "[SHI07] on " + shiftName );

                if (shift.operations[shift.operations.Length - 1].TrailerQuantity != shift.EndTrailerQuantity)
                {
                    Console.WriteLine("[ SHI07 : checkShifts ] : 'EndTrailerQuantity' for shift[" + indexShift + "] non coherent "
                                      + "with lastOperation : " + lastQuantity + " (lastQuantity) != " + shift.EndTrailerQuantity +
                                      " (lastShiftEndTrailerQuantity).");
                    value = false;
                }

                if (!Floating.Equal(lastTrailerQuantity[shiftTrailer.index], shift.StartTrailerQuantity))
                {
                    Console.WriteLine("[ SHI07 : checkShifts ] : 'StartTrailerQuantity' for shift[" + indexShift + "] non coherent "
                                      + "with lastShift of this trailer : " + lastTrailerQuantity[shiftTrailer.index] +
                                      " (lastQuantity) != " + shift.StartTrailerQuantity + " (lastShiftStartTrailerQuantity).");
                    value = false;
                }

                lastTrailerQuantity[shiftTrailer.index] = lastQuantity;

                #endregion

                indexShift++;
            }

            return value;
        }


        /// <summary>
        /// [ SHI11 ] The quantity delivered at a customer must be positive 
        /// and the quantity loaded at a source must be positive too. This 
        /// implies that the sign of the quantity must be positive for a 
        /// customer and negative for a source.</summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param> 
        /// 
        /// <returns>True if SHI11 are OK.</returns>
        /// 
        internal bool checkSHI11(IRP_Roadef_Challenge_Shift shift, int indexShift)
        {
            bool value = true;

            //Console.WriteLine( "[SHI11] on " + shiftName );

            for (int i = 0; i < shift.operations.Length - 1; i++)
            {
                Operation operation = shift.operations[i];
                int indexOperation = i;
                int site = operation.point;

                if (site > input.customers.Length + input.sources.Length + 1)
                {
                    return false; // already checked and traced before
                }

                if ((site < input.sources.Length + 1 && site > 0) && Floating.StrictlyGreater(operation.Quantity, 0))
                {
                    Console.WriteLine("[ SHI11 : checkShifts ] : quantity ( "
                                      + operation.Quantity + " ) has wrong sign on the source operation[ "
                                      + indexOperation + " ] of shift[ " + indexShift + " ].");

                    value = false;
                }
                else if (site >= input.sources.Length + 1 && site <= input.sources.Length + input.customers.Length + 1 && Floating.StrictlyGreater(0, operation.Quantity))
                {
                    Console.WriteLine("[ SHI11 : checkShifts ] : quantity ( "
                                      + operation.Quantity + " ) has wrong sign on the customer operation[ "
                                      + indexOperation + " ] of shift[ " + indexShift + " ].");

                    value = false;
                }
            }

            return value;
        }


        /// <summary>
        /// [SHI16| Capacity at the customer's site]
        /// For each delivery operation o in a shift s, the delivered quantity must be smaller than the customer tank capacity.
        /// </summary>
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param> 
        /// 
        /// <returns>True if SHI16 is OK.</returns>
        internal bool checkSHI16(IRP_Roadef_Challenge_Shift shift, int indexShift)
        {
            bool value = true;
            for (int i = 0; i < shift.operations.Length - 1; i++)
            {
                int indexOperation = i;

                Operation operation = shift.operations[i];
                int cust = operation.point;
                if (cust < input.sources.Length + 1) continue;
                if ( input.customers[cust - (input.sources.Length + 1)].callIn == 1) continue;// SHI16 only applies on customers
                if (Floating.StrictlyGreater(operation.Quantity, input.customers[cust - (input.sources.Length + 1)].Capacity))
                {
                    Console.WriteLine("[ SHI16 : checkShifts ] : the quantity delivered at operation [ " + indexOperation
                                      + " ] of shift[ " + indexShift + " ] for Customer [ " + cust + " ] - is too big (" + operation.Quantity + " > " +
                                     input.customers[cust - (input.sources.Length + 1)].Capacity + ").");

                    value = false;
                }

                if (Floating.StrictlyLower(operation.Quantity, input.customers[cust - (input.sources.Length + 1)].MinOperationQuantity))
                {
                    Console.WriteLine("[ SHI16 : checkShifts ] : the quantity delivered at operation [ " + indexOperation
                                      + " ] of shift[ " + indexShift + " ] for Customer [ " + cust + " ] - is too small (" + operation.Quantity + " < " +
                                     input.customers[cust - (input.sources.Length + 1)].MinOperationQuantity + ").");

                    value = false;
                }

            }
            return value;
        }

        #endregion

        #endregion


        #region Checkers on Sites Constraints

        /// <summary>
        /// [ DYN01: Inventory at different points (source or customer except for call-in customers)
        /// is modified after each timestep by forecasted consumption/production and possibly
        /// delivery/loadingFor each Sites of the output file, check all constraints ] : 
        /// For each point p, tankquantity at time step h is the bulk quantity at previous
        /// timestep plus delivered quantity minus consumption (forecast). This quantity 
        /// is bounded to remain within [0,CAPACITY]..
        /// 
        internal bool checkSites()
        {
            bool value = true;

            #region DYN01

            double[][] operationQuantities = new double[1 + input.sources.Length + input.customers.Length][];

            foreach (IRP_Roadef_Challenge_SiteInventory siteInventory in output.Inventories)
            {
                if (siteInventory == null) continue;
                operationQuantities[siteInventory.site] = new double[input.horizon];
            }

            int indexShift = 0;

            foreach (IRP_Roadef_Challenge_Shift shift in output.Shifts)
            {
                int indexOperation = 0;

                foreach (Operation operation in shift.operations)
                {
                    if (indexOperation < shift.operations.Length - 1)
                    {
                        int site = operation.point;


                        if (site > input.customers.Length + input.sources.Length + 1)
                        {
                            Console.WriteLine("[ DYN01 : checkSites ] : Operation[" + indexOperation
                                              + "] of shift[" + indexShift + "] not a site.");
                            return false;
                        }

                        int operationTS = operation.arrival / input.unit;

                        if ((site >= input.sources.Length + 1 && site < input.sources.Length + input.customers.Length + 1))
                            operationQuantities[operation.point][operationTS] += operation.Quantity;


                        if ((site >= input.sources.Length + 1 && site < input.sources.Length + input.customers.Length + 1) && Floating.StrictlyGreater(0, operationQuantities[operation.point][operationTS]))
                        {
                                Console.WriteLine("[ DYN01 : checkSites ] : Customer[" + operation.point
                                                  + "] negative 'delivered quantities' instead of positive value expected at step[" + operationTS +
                                                  "].");
                                value = false;   
                        }
                    }
                    indexOperation++;
                }
                indexShift++;
            }

            foreach (IRP_Roadef_Challenge_SiteInventory siteInventory in output.Inventories)
            {
                //Console.WriteLine( "*********** [ checkSites ] : check site[" + siteInventory.site + "] ***********" );
                if (siteInventory == null) continue;
                int site = siteInventory.site;
                             
                if (site > input.customers.Length + input.sources.Length + 1)
                {
                    Console.WriteLine("[ DYN01 : checkSites ] : SiteInventory[" + siteInventory.site
                                      + "] are not on a site.");
                    return false;
                }

                //Console.WriteLine( "[ DYN01 : checkSites ] on site[" + siteInventory.site + "]" );



                if ((site >= input.sources.Length + 1 && site < input.sources.Length + input.customers.Length + 1))
                {
                    if (input.customers[site - (input.sources.Length + 1)].callIn == 1) continue;

                    for (int i = 0; i < siteInventory.TankQuantity.Length; i++)
                    {
                        if (Floating.StrictlyNegative(siteInventory.TankQuantity[i]))
                        {
                            Console.WriteLine("[ DYN01 : checkSites ] : SiteInventory[" + siteInventory.site
                                              + "] not respected at step[" + i + "] : " + siteInventory.TankQuantity[i] +
                                              " (tankQuantity) < 0.");
                            value = false;
                        }

                        if (Floating.StrictlyGreater(siteInventory.TankQuantity[i], input.customers[site - (input.sources.Length + 1)].Capacity))
                        {
                            Console.WriteLine("[ DYN01 : checkSites ] : SiteInventory[" + siteInventory.site
                                              + "] not respected at step[" + i + "] : " + siteInventory.TankQuantity[i] +
                                              " (tankQuantity) > " + input.customers[site - (input.sources.Length + 1)].Capacity + ".");
                            value = false;
                        }
                    }
                }
            }

            #endregion

            return value;
        }

        #endregion


        #region Checkers on Resources Constraints

        /// <summary>
        /// For each resources of the output file, check all constraints.</summary>
        /// 
        /// <returns>True if all resources are OK.</returns>
        /// 
        internal bool checkResources()
        {
            bool value = true;

            int indexShift = 0;

            int[] endOfLastShiftForDrivers = new int[input.drivers.Length];
            int[] endOfLastShiftForTrailers = new int[input.trailers.Length];

            foreach (IRP_Roadef_Challenge_Shift shift in output.Shifts)
            {
                //Console.WriteLine( "*********** [ checkResources ] : check Shift[" + indexShift + "] ***********" );

                IRP_Roadef_Challenge_Instance_driver shiftDriver = null;
                if (!getDriver(shift, ref shiftDriver)) return false;


                IRP_Roadef_Challenge_Instance_Trailers shiftTrailer = null;
                if (!getTrailer(shift, ref shiftTrailer)) return false;

                // Not Optimal checker but all these following checks could be called independantly  

                // DRIVERS

                value = value & checkDR01(shift, indexShift, shiftDriver, endOfLastShiftForDrivers[shiftDriver.index]);

                value = value & checkDR03(shift, indexShift, shiftDriver);

                value = value & checkDR08(shift, indexShift, shiftDriver);

                // TRAILERS 

                value = value & checkTL01(shift, indexShift, shiftTrailer, endOfLastShiftForTrailers[shiftTrailer.index]);

                value = value & checkTL03(shift, indexShift, shiftDriver, shiftTrailer);

                // Record Last Shift Ending Dates

                endOfLastShiftForDrivers[shiftDriver.index] = shift.end;
                endOfLastShiftForTrailers[shiftTrailer.index] = shift.end;

                indexShift++;
            }

            return value;
        }

        #region Subcheckers on Drivers Constraints

        /// <summary>
        /// [ DR01 : Shifts separation ] :  For each driver d, two consecutive shifts assigned to d 
        /// must be separated by a delay of minInterSHIFTDURATION(d). </summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param> 
        /// <param name="shiftDriver">Driver of the shift.</param>
        /// <param name="endOfLastShift">End of the last shift of this driver.</param>
        /// 
        internal static bool checkDR01(IRP_Roadef_Challenge_Shift shift, int indexShift, IRP_Roadef_Challenge_Instance_driver shiftDriver, int endOfLastShift)
        {
            bool value = true;

            //Console.WriteLine( "[DRIO1] on " + shiftName );

            if (endOfLastShift != 0
                && shift.start < endOfLastShift + shiftDriver.minInterSHIFTDURATION)
            {
                Console.WriteLine("[ DRI01 : checkDrivers ] : Driver[" + shiftDriver.index
                                  + "] doesn't respect 'minInterSHIFTDURATION' before shift[" + indexShift + "] : "
                                  + endOfLastShift + " (endLastShift) + " + shiftDriver.minInterSHIFTDURATION
                                  + " (minInterSHIFTDURATION) < " + shift.start + " (shiftStart).");
                value = false;
            }

            return value;
        }



        /// <summary>
        /// [ DR03 : Respect of maximal driving time ] : For each shift s and operation o 
        /// (including the final fake operation), the cumulated driving time is either the 
        /// one of the previous point plus travel time from this point, or the travel time since 
        /// the last layover if layovers have been taken since last point.</summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param> 
        /// <param name="shiftBase">Base of the shift.</param> 
        /// <param name="shiftTractor">Tractor of the shift.</param> 
        /// <param name="shiftDriver">Driver of the shift.</param> 
        /// 
        internal bool checkDR03(IRP_Roadef_Challenge_Shift shift, int indexShift, IRP_Roadef_Challenge_Instance_driver shiftDriver)
        {
            bool value = true;

            //Console.WriteLine( "[DRIO3] on " + shiftName );

            if (shift.operations[0].layoverbefore == 1)
            {
                if ( shift.operations[0].drivingtimebeforelayover > shiftDriver.maxDrivingDuration)
                {
                    Console.WriteLine("[ DRI03 : checkDrivers ] : operation[" + 0
                                      + "] doesn't respect the 'maxDrivingDuration' constraint for shift[" + indexShift + "] : "
                                      + shift.operations[0].drivingtimebeforelayover + " (computed drivingtimebeforelayover) > "
                                      + shiftDriver.maxDrivingDuration + " (maxDrivingDuration).");
                    value = false;
                }
            }
            else
            {
                if (shift.operations[0].cumulatedDrivingTime > shiftDriver.maxDrivingDuration)
                {
                    Console.WriteLine("[ DRI03 : checkDrivers ] : operation[" + 0
                                      + "] doesn't respect the 'maxDrivingDuration' constraint for shift[" + indexShift + "] : "
                                      + shift.operations[0].cumulatedDrivingTime + " (computed cumulatedDrivingTime) > "
                                      + shiftDriver.maxDrivingDuration + " (maxDrivingDuration).");
                    value = false;
                }
            }




            for (int op = 1; op < shift.operations.Length; op++)
            {
                if (shift.operations[op].layoverbefore == 1)
                {
                    if (shift.operations[op - 1].cumulatedDrivingTime + shift.operations[op].drivingtimebeforelayover > shiftDriver.maxDrivingDuration)
                    {
                        Console.WriteLine("[ DRI03 : checkDrivers ] : operation[" + op
                                          + "] doesn't respect the 'maxDrivingDuration' constraint for shift[" + indexShift + "] : "
                                          + shift.operations[op - 1].cumulatedDrivingTime + shift.operations[op].drivingtimebeforelayover + " (computed drivingtimebeforelayover) > "
                                          + shiftDriver.maxDrivingDuration + " (maxDrivingDuration).");
                        value = false;
                    }
                }
                else
                {
                    if (shift.operations[op].cumulatedDrivingTime > shiftDriver.maxDrivingDuration)
                    {
                        Console.WriteLine("[ DRI03 : checkDrivers ] : operation[" + op
                                          + "] doesn't respect the 'maxDrivingDuration' constraint for shift[" + indexShift + "] : "
                                          + shift.operations[op].cumulatedDrivingTime + " (computed cumulatedDrivingTime) > "
                                          + shiftDriver.maxDrivingDuration + " (maxDrivingDuration).");
                        value = false;
                    }
                }
            }
         
            return value;
        }





        /// <summary>
        /// [ DR08 : Time windows of the drivers ] : For each shift s, 
        /// the full [start(s),end(s)] interval must fit in one 
        /// of the time-windows of the drivers.</summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param> 
        /// <param name="shiftDriver">Driver of the shift.</param>
        /// 
        internal static bool checkDR08(IRP_Roadef_Challenge_Shift shift, int indexShift, IRP_Roadef_Challenge_Instance_driver shiftDriver)
        {
            bool value = true;

            //Console.WriteLine( "[DRIO8] on " + shiftName );

            int s = shift.start;
            int e = shift.end;
            bool found = false;
            int i = 0;
            while (i < shiftDriver.timewindows.Length && !found)
            {
                if (s >= shiftDriver.timewindows[i].start && e <= shiftDriver.timewindows[i].end) found = true;
                i++;
            }
            if (!found)
            {
                Console.WriteLine("[ DRI08 : checkDrivers ] : shift[" + indexShift
                                  + "] is not in a driver TimeWindows  : "
                                  + s + " (start) ; " + e + " (end).");
                value = false;
            }

            return value;
        }


        #endregion

        #region Subcheckers on Trailers Constraints

        /// <summary>
        /// [ TL01 : Different shifts of the same trailer cannot overlap in time ] :  
        /// For each trailer, if we consider two shifts s1 and s2 performed by
        /// this trailer, either s1 ends before the start of s2 or s2
        /// ends before the start of s1.</summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param>  
        /// <param name="shiftTrailer">Trailer of this shift.</param>  
        /// <param name="endOfLastShift">End of lastShift of this trailer.</param> 
        /// 
        internal static bool checkTL01(IRP_Roadef_Challenge_Shift shift, int indexShift, IRP_Roadef_Challenge_Instance_Trailers shiftTrailer, int endOfLastShift)
        {
            bool value = true;

            //Console.WriteLine( "[TL01] on " + shiftName );

            if (endOfLastShift != 0
                && shift.start < endOfLastShift)
            {
                Console.WriteLine("[ TL01 : checkTrailers ] : Trailer[" + shiftTrailer.index
                                  + "] doesn't respect shift separation before shift[" + indexShift + "] : "
                                  + endOfLastShift + " (endLastShift) < " + shift.start + " (shift Start).");
                value = false;
            }

            return value;
        }


        /// <summary>
        /// [ TL03 : The trailer attached to a driver in a shift must be compatible ] :  
        /// For each shift s, the assigned trailer must the trailer that can be drive by the driver.</summary>
        /// 
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param>  
        /// <param name="shiftTractor">driver of this shift.</param>  
        /// <param name="shiftTrailer">Trailer of this shift.</param>  
        /// 
        internal static bool checkTL03(IRP_Roadef_Challenge_Shift shift, int indexShift, IRP_Roadef_Challenge_Instance_driver shiftDriver, IRP_Roadef_Challenge_Instance_Trailers shiftTrailer)
        {
            bool value = true;

            //Console.WriteLine( "[TL03] on " + shiftName );
            bool trailerOk = false;
            foreach (int tl in shiftDriver.trailer)
            {
                if (shiftTrailer.index == tl) trailerOk = true;               
            }

            
            if (!trailerOk)
            {
                Console.WriteLine("[ TL03 : checkTrailers ] : 'trailer' of shift[" + indexShift +
                                  "] is not in the set of driverTrailers : "
                                  + "trailer[" + shiftTrailer.index + "] and driver[" + shiftDriver.index + "].");
                value = false;
            }

            return value;
        }

  

        #endregion

        #endregion


        #region Subcheckers of Constraints related to the quality of service


        /// <summary>
        /// Check runout.</summary>
        /// 
        /// <returns>True if we don't have  runout.</returns>
        /// 
        internal bool checkServiceQuality()
        {
            bool value = true;
            value = value & checkQS01();
            value = value & checkQS02();
            value = value & checkQS03();
            return value;
        }

        /// <summary>
        /// [ QS01 : Orders satisfaction ] :  
        /// All the orders having a time windows ending before the planning horizon
        /// should be satisfied.</summary>
        /// 
        internal bool checkQS01()
        {
            bool value = true;

            #region MissedOrder check

            //Console.WriteLine( "*********** [ checkQS01 ] : check Missed Orders ***********" );
#if DEBUG
            int nbOrders = 0;
            int nbRealOrders = 0;
            int nbSatisfiedOrders = 0;
#endif

            int nbMissedOrders = 0;

            int[][] ordersCustomers = new int[input.customers.Length][];
            double[][] DeliveredordersCustomers = new double[input.customers.Length][];

            for (int c = 0; c < input.customers.Length; c++)
            {
                IRP_Roadef_Challenge_Instance_Customers customer = input.customers[c];

                if (input.customers[c].callIn == 1 && input.customers[c].orders!=null)
                { 
                   ordersCustomers[c] = new int[customer.orders.Length];
                   DeliveredordersCustomers[c] = new double[customer.orders.Length];
                    for (int o = 0; o < customer.orders.Length; o++)
                    {
                        Order order = customer.orders[o];

                        if (order.latestTime > NbMinutesMissedOrdersHorizon)
                        {
                            ordersCustomers[c][o] = 0;
                            DeliveredordersCustomers[c][o] = 0;
                        }
                        else
                        {
                            ordersCustomers[c][o] = -1;
                            DeliveredordersCustomers[c][o] = 0;
#if DEBUG
                        nbRealOrders++;
#endif
                        }
#if DEBUG
                    nbOrders++;
#endif
                    }
                }
            }

            int offsetCustomers = 1 + input.sources.Length;


            foreach (IRP_Roadef_Challenge_Shift shift in output.Shifts)
            {
                foreach (Operation operation in shift.operations)
                {
                    if (operation.point >= offsetCustomers)
                    {
                        if (input.customers[operation.point - offsetCustomers].callIn == 1 && input.customers[operation.point - offsetCustomers].orders != null)
                        {
                            int or = 0;
                            foreach (Order order in input.customers[operation.point - offsetCustomers].orders)
                            {
                                if (order.earliestTime <= operation.arrival  && operation.arrival <= order.latestTime)
                                {
                                    DeliveredordersCustomers[operation.point - offsetCustomers][or] = DeliveredordersCustomers[operation.point - offsetCustomers][or] + operation.Quantity;                                   
                                }                               
                                or++;
                            }                         
                        }
                    }
                }
            }

            for (int c = 0; c < input.customers.Length; c++)
            {
                if (input.customers[c].orders != null)
                {
                    for (int o = 0; o < input.customers[c].orders.Length; o++)
                    {
                        if (Floating.Greater(DeliveredordersCustomers[c][o], input.customers[c].orders[o].Quantity * input.customers[c].orders[o].orderQuantityFlexibility / 100) && Floating.Lower(DeliveredordersCustomers[c][o], input.customers[c].orders[o].Quantity))
                        {
                            ordersCustomers[c][o] = 1;
                        }
                        else
                        {
                            int cust = c + offsetCustomers;
                            Console.WriteLine("[ checkQS01 MissedOrder ] : Missed Order[" + o + "] of the customer[" + cust + "]");
                        }
                    }
                }
            }

            for (int c = 0; c < input.customers.Length; c++)
            {
                IRP_Roadef_Challenge_Instance_Customers customer = input.customers[c];
                if (input.customers[c].orders != null)
                {
                    for (int o = 0; o < customer.orders.Length; o++)
                    {
                        if (ordersCustomers[c][o] == -1) nbMissedOrders++;
#if DEBUG
                        else if (ordersCustomers[c][o] == 1) nbSatisfiedOrders++;
#endif
                    }
                }
            }

#if DEBUG
            Console.WriteLine(nbSatisfiedOrders + " orders satisfied over " + nbOrders + ".");

            Console.WriteLine("number of orders : {0}, number of orders optimized in horizon planning : {1}",
                nbOrders, nbRealOrders);

            Console.WriteLine("number of satisfied orders : {0},number of missed orders : {1}",
                nbSatisfiedOrders, nbMissedOrders);
#endif


            if (nbMissedOrders != 0)
            {
                Console.WriteLine("[ checkQS01 MissedOrder ] : number of missed order:  "
                                  + "computed totalMissedOrderCosts : "
                                  + nbMissedOrders);
                value = false;
            }

            #endregion

            return value;
        }

        /// [ QS02 : Run-out avoidance] :  
        /// For each VMI customer p, the tank level should be always grater or equal to the autonomy level
        /// SafetyLevel(P) at each time step over the planning horizon.</summary>

        internal bool checkQS02()
        {
            bool value = true;

            #region Runout check

            //Console.WriteLine( "*********** [ checkCosts ] : check TotalRunoutCosts ***********" );
            int runoutsNbre = 0;
            int indexInventory = 0;

            foreach (IRP_Roadef_Challenge_SiteInventory siteInventory in output.Inventories)
            {
                if (siteInventory == null) continue;
                int site = siteInventory.site;
                int inventoryRunOutNbre = 0;

                if (site > input.customers.Length + input.sources.Length + 1)
                {
                    Console.WriteLine("[ checkCosts TotalRunoutCosts ] : siteInventory[" + indexInventory + "] is not on a site.");
                    return false;
                }

                if ((site >= input.sources.Length + 1) && (site < input.customers.Length + input.sources.Length + 1))
                {
                    // Runouts checking on customers only

                    int customer = site;
                    if (input.customers[customer - (input.sources.Length + 1)].callIn == 0)
                    {
                        for (int i = 0; i < input.horizon; i++)
                        {
                            if (Floating.StrictlyLower(siteInventory.TankQuantity[i], input.customers[customer - (input.sources.Length + 1)].SafetyLevel))
                            {
                                if (Floating.StrictlyGreater(1, (int.MaxValue - inventoryRunOutNbre)))
                                    inventoryRunOutNbre = int.MaxValue;
                                else
                                    inventoryRunOutNbre++;
                            }
                        }
                    }
                }
                runoutsNbre += inventoryRunOutNbre;
                indexInventory++;
            }

            if (runoutsNbre != 0)
            {
                Console.WriteLine("[ check  TotalRunOut  ] :Total runout number "
                                  + runoutsNbre);
                value = false;
            }

            #endregion

            return value;
        }


        /// [ QS03 : Orders satisfaction ] :  
        /// Each operation on a call-in customer should be related to an order, meaning no operations are possible
        /// if there is any related order.</summary>
        /// 
        internal bool checkQS03()
        {
            int indexShift = 0;
            bool value = true;
            foreach (IRP_Roadef_Challenge_Shift shift in output.Shifts)
            {
                //Console.WriteLine( "*********** [ checkQualityServices ] : check Shift[" + indexShift + "] ***********" );

                value = value & subcheckQS03(shift, indexShift);

                indexShift++;
            }
            return value;
        }

        #region subcheckQS03
        /// <summary>
        /// [ subcheckQS03 : Each operation on a call-in customer should be related to an order, 
        /// meaning no operations are possible if there is any related order.</summary>
        /// <param name="shift">Checked Shift.</param>
        /// <param name="indexShift">Shift index.</param>        
        /// <returns>True if subcheckQS03 are OK.</returns>
        /// 
        internal bool subcheckQS03(IRP_Roadef_Challenge_Shift shift, int indexShift)
        {
            bool value = true;

            //Console.WriteLine( "[QS03] on " + shiftName );

            int indexOperation = 0;

            foreach (Operation operation in shift.operations)
            {
                // All Operations but not the last one.
                if (indexOperation < shift.operations.Length - 1)
                {
                    // Controls already perform on operationSite.

                    int site = operation.point;

                    if (site < 0 || site >= 1 + input.sources.Length + input.customers.Length)
                    {
                        Console.WriteLine("[ QS03 : checkShifts ] : operation[" + indexOperation + "] of shift["
                                          + indexShift + "] not on a site.");
                        return false;
                    }

                    if (site >= 1 + input.sources.Length)
                    {
                        if (input.customers[site - (1 + input.sources.Length)].callIn == 1)
                        {
                            if (input.customers[site - (1 + input.sources.Length)].orders == null) continue;

                            bool twFound = false;

                            int indTw = 0;

                            while (indTw < input.customers[site - (1 + input.sources.Length)].orders.Length && !twFound)
                            {
                                Order od = input.customers[site - (1 + input.sources.Length)].orders[indTw];
                                if (od.earliestTime <= operation.arrival && od.latestTime >= operation.arrival) twFound = true;
                                indTw++;
                            }

                            if (!twFound)
                            {
                                Console.WriteLine("[QS03 : checkShifts ] : operation arrival[" + indexOperation + "] of shift["
                                                  + indexShift + "] is out of the"
                                                  + " timewindows of orders of site[" + site + "] ==> " + operation.arrival + " (operationStart)");
                                value = false;
                            }
                        }
                    }
                }
                indexOperation++;
            }

            return value;
        }

        #endregion


        #endregion


        #region Checkers on Costs

        /// <summary>
        /// Check all costs.</summary>
        /// 
        /// <returns>True if all costs are OK.</returns>
        /// 
        internal bool checkCosts()
        {
            bool value = true;

            // TODO : all costs should be checked independently using only input/output data structures

            #region TotalQuantity & TotalShiftCosts

            //Console.WriteLine( "*********** [ checkCosts ] : check TotalQuantity & TotalShiftCosts ***********" );

            double deliveredQuantities = 0;
            double layoverCosts = 0;
            //int totalWorkingTime = 0;
            double totalTimeCosts = 0;
            double totalDistance = 0;
            double distanceCosts = 0;
            int indexShift = 0;

            foreach (IRP_Roadef_Challenge_Shift shift in output.Shifts)
            {
                String shiftName = "Shift[" + indexShift + "]";

                IRP_Roadef_Challenge_Instance_driver shiftDriver = null;
                if (!getDriver(shift, ref shiftDriver)) return false;

                IRP_Roadef_Challenge_Instance_Trailers shiftTrailer = null;
                if (!getTrailer(shift, ref shiftTrailer)) return false;

                int indexOperation = 0;
                double shiftDistanceCosts = 0;

                int lastGeoCode = 0;

                int shiftWorkingTime = shift.end - shift.start;

                int nblayover = 0;
                foreach (Operation operation in shift.operations)
                {
                    if (operation.layoverbefore == 1)
                    {
                        nblayover++;
                    }
                }

                shiftWorkingTime = shiftWorkingTime - nblayover * shiftDriver.LayoverDuration;


                //int LastLayoverEnd = shift.start;

                foreach (Operation operation in shift.operations)
                {
                    #region operationCosts

                    // distance costs
                    int pt = operation.point;
                    var distance = input.DistMatrices[lastGeoCode][pt];
                    totalDistance += distance;
                    var vehicleDistanceCost = shiftTrailer.DistanceCost;
                    shiftDistanceCosts += distance * vehicleDistanceCost;
                    distanceCosts += distance * vehicleDistanceCost;
                    indexOperation++;

                    lastGeoCode = pt;

                    #endregion
                    if (pt < input.customers.Length + input.sources.Length + 1 && pt >= input.sources.Length + 1)
                    {
                        deliveredQuantities += operation.Quantity;
                    }
                }

                //totalWorkingTime += shiftWorkingTime;
                double shiftTimeCosts = 0;
                double shiftLayoverCosts = 0;
                shiftTimeCosts += shiftWorkingTime * shiftDriver.TimeCost;
                shiftLayoverCosts = nblayover * shiftDriver.LayoverCost;
                layoverCosts += shiftLayoverCosts;
                totalTimeCosts += shiftTimeCosts;

                #region shiftCosts



                // shiftDistanceCosts
                if (!Floating.Equal(shiftDistanceCosts, shift.DistanceCosts))
                {
                    Console.WriteLine("[ checkCosts ] : 'DistanceCosts' doesn't fit the "
                                      + "computed 'shiftDistanceCosts' for " + shiftName + " : " + shiftDistanceCosts +
                                      " (computed distance costs)  != "
                                      + shift.DistanceCosts + "(shift distance costs)");
                    value = false;
                }


                // shiftTimeCosts
                if (!Floating.Equal(shiftTimeCosts, shift.TimeCosts))
                {
                    Console.WriteLine("[ checkCosts ] : 'TimeCosts' doesn't fit the "
                                      + "computed 'shiftTimeCosts' for " + shiftName + " : " + shiftTimeCosts +
                                      " (computed time costs)  != "
                                      + shift.TimeCosts + "(shift time costs)");
                    value = false;
                }

                // shiftLayoverCosts
                if (!Floating.Equal(shiftLayoverCosts, shift.LayoverCosts))
                {
                    Console.WriteLine("[ checkCosts ] : 'LayoverCosts' doesn't fit the "
                                      + "computed 'shiftLayoverCosts' for " + shiftName + " : " + shiftLayoverCosts +
                                      " (computed layover costs)  != "
                                      + shift.LayoverCosts + "(shift time costs)");
                    value = false;
                }

                indexShift++;

                #endregion

            }

            #region DeliveredQuantities

            // Check Delivered Quantities

            if (!Floating.Equal(deliveredQuantities, output.DeliveredQuantities))
            {
                Console.WriteLine("[ checkCosts totalQuantity ] : 'totalQuantity' doesn't fit the "
                                  + "computed 'deliveredQuantities' : " + deliveredQuantities +
                                  " (computed delivered quantities)  != "
                                  + output.DeliveredQuantities + "(ouput total quantity)");
                value = false;
            }

            #endregion

            #region TotalShiftCosts

            // Check TotalShiftCosts

            double totalShiftCosts = distanceCosts
                + layoverCosts + totalTimeCosts;

            if (!Floating.Equal(totalShiftCosts, output.TotalShiftsCosts))
            {
                Console.WriteLine("[ checkCosts totalShiftCosts ] : 'totalShiftCosts' doesn't fit the "
                                  + distanceCosts +
                                  " (computed distance costs) + " +
                                  layoverCosts + " (computed layover costs) + " +
                                  totalTimeCosts
                                  + " (computed time costs) = "
                                  + " (computed total shift costs) != " + output.TotalShiftsCosts + " (ouput total shift costs).");
                value = false;
            }

            #endregion


            #endregion

#if TRACE
            computeCosts(input, output);
#endif
            return value;
        }

        /// <summary>
        /// Compute all costs for shifts ending before the given time.</summary>
        /// 
        public void computeCosts(IRP_Roadef_Challenge_Instance input, IRP_Roadef_Challenge_Output output)
        {
            #region RC

            var nbTimestepsRunout = 0;

            foreach (var siteInventory in output.Inventories)
            {
                if (siteInventory == null) continue;
                var customer = input.customers[siteInventory.site - (input.sources.Length + 1)];
                for (var i = 0; i < input.horizon; i++)
                {
                    if (Floating.Greater(siteInventory.TankQuantity[i], customer.SafetyLevel)) continue;
                    nbTimestepsRunout++;
                }
            }

            //Console.WriteLine("RN = {1}", nbTimestepsRunout);

            #endregion

            #region LR

            var planningHorizon = input.horizon;
            var nbMinutesPlanningHorizon = planningHorizon * input.unit;

            double shiftCosts = 0.0d;
            var deliveredQuantity = 0.0d;

            foreach (IRP_Roadef_Challenge_Shift shift in output.Shifts)
            {
                if (shift.start >= nbMinutesPlanningHorizon) continue;

                shiftCosts += shift.getCost();

                foreach (Operation operation in shift.operations)
                {
                    int customer = operation.point;

                    if (customer < input.customers.Length + input.sources.Length + 1 && customer >= input.sources.Length + 1)
                    {
                        deliveredQuantity += operation.Quantity;
                    }
                }
            }

            double logisticRatio = 0.0d;
            if (Floating.StrictlyGreater(deliveredQuantity, 0)) logisticRatio = shiftCosts / deliveredQuantity;


            Console.WriteLine("\n\n\n**********************************************************************");
            Console.WriteLine("**********************************************************************");
            Console.WriteLine("******* Horizon = {3,4} ({4,2} days) ************************************* \n        Logistic Ratio = {0,8:0.000000}, \n        Total Shifts Cost = {1,8:0.00}, \n        Total Delivered Quantity  = {2,8}",
              logisticRatio, shiftCosts, deliveredQuantity, planningHorizon, planningHorizon / 24);
            Console.WriteLine("**********************************************************************");
            Console.WriteLine("**********************************************************************\n\n");
         


            #endregion
        }

        #endregion


        #region Tools

        /// <summary>
        /// Get the driver of a shift and check if everything is OK.</summary>
        /// 
        /// <param name="shift">The shift.</param>
        /// <param name="shiftDriver">The shift driver to assign.</param>
        /// 
        /// <returns>True if shiftDriver has been correctly assigned.</returns>
        /// 
        internal bool getDriver(IRP_Roadef_Challenge_Shift shift, ref IRP_Roadef_Challenge_Instance_driver shiftDriver)
        {
            if (shift.driver < 0)
            {
                Console.WriteLine("[ checkShifts ] : Positive or null value expected for 'driverIndex' of shift[" + shift.index +
                                  "] => " + shift.driver + ".");
                return false;
            }
            else
            {
                bool found = false;
                int indDriver = 0;
                while (indDriver < input.drivers.Length && !found)
                {
                    IRP_Roadef_Challenge_Instance_driver inputDriver = input.drivers[indDriver];
                    if (inputDriver.index == shift.driver) found = true;
                    indDriver++;
                }
                if (!found)
                {
                    Console.WriteLine("[ checkShifts ] : driverIndex not in set of drivers for shift[" + shift.index + "] => " +
                                      shift.driver + ".");
                    return false;
                }
                shiftDriver = input.drivers[shift.driver];
            }

            return true;
        }


        /// <summary>
        /// Get the trailer of a shift and check if everything is OK.</summary>
        /// 
        /// <param name="shift">The shift.</param>
        /// <param name="shiftTrailer">The shift trailer to assign.</param>
        /// 
        /// <returns>True if shiftTrailer has been correctly assigned.</returns>
        /// 
        internal bool getTrailer(IRP_Roadef_Challenge_Shift shift, ref IRP_Roadef_Challenge_Instance_Trailers shiftTrailer)
        {
            if (shift.trailer < 0)
            {
                Console.WriteLine("[ checkShifts ] : Positive or null value expected for 'trailerIndex' of shift[" + shift.index +
                                  "] => " + shift.trailer + ".");
                return false;
            }
            else
            {
                bool found = false;
                int indTrailer = 0;
                while (indTrailer < input.trailers.Length && !found)
                {
                    IRP_Roadef_Challenge_Instance_Trailers inputTrailer = input.trailers[indTrailer];
                    if (inputTrailer.index == shift.trailer) found = true;
                    indTrailer++;
                }
                if (!found)
                {
                    Console.WriteLine("[ checkShifts ] : 'trailerIndex' not in set of trailers for shift[" + shift.index + "] => " +
                                      shift.trailer + ".");
                    return false;
                }
                shiftTrailer = input.trailers[shift.trailer];
            }

            return true;
        }


        /// <summary>
        /// Return the previous shift for this trailer (if any)
        /// </summary>
        /// <param name="shift">A shift.</param>
        /// <returns>The previous shift if any, null otherwise.</returns>
        private IRP_Roadef_Challenge_Shift getPrevTrailerShift(IRP_Roadef_Challenge_Shift shift)
        {
            int latestend = -1;
            IRP_Roadef_Challenge_Shift latestPrev = null;
            foreach (IRP_Roadef_Challenge_Shift sh in output.Shifts)
            {
                // skip shift of other trailer or ending after the start of the considered shift
                if (sh == shift || sh.trailer != shift.trailer || sh.end > shift.start) continue;
                if (sh.end > latestend)
                {
                    latestPrev = sh;
                    latestend = sh.end;
                }
            }
            return latestPrev;
        }


        /// <summary>
        /// Return the next shift for this trailer (if any)
        /// </summary>
        /// <param name="shift">A shift.</param>
        /// <returns>The next shift if any, null otherwise.</returns>
        private IRP_Roadef_Challenge_Shift getNextTrailerShift(IRP_Roadef_Challenge_Shift shift)
        {
            int earliestStart = input.getLatestTime() + 1;
            IRP_Roadef_Challenge_Shift earliestNext = null;
            foreach (IRP_Roadef_Challenge_Shift sh in output.Shifts)
            {
                // skip shift of other trailer or starting before the end of the considered shift
                if (sh == shift || sh.trailer != shift.trailer || sh.start < shift.end) continue;
                if (sh.start < earliestStart)
                {
                    earliestNext = sh;
                    earliestStart = sh.start;
                }
            }
            return earliestNext;
        }


        /// <summary>
        /// Return the ranking matrix of shifts performed by each trailer
        /// </summary>
        /// <param name="shift">A shifts[].</param>
        /// <returns>matrix of shifts performed by each trailer.</returns>

        internal int[][] shifts_performed_by_each_trailer(IRP_Roadef_Challenge_Shift_[] shift)
        {
            int[][] shift_performed_by_trailer = new int[input.trailers.Length][];
            int[] number_of_shifts_performed_by_trailer = new int[input.trailers.Length];

            foreach (IRP_Roadef_Challenge_Shift_ sh in shift)
            {
                number_of_shifts_performed_by_trailer[sh.trailer]++;
            }

            for (int tl = 0; tl < input.trailers.Length; tl++)
            {
                shift_performed_by_trailer[tl] = new int[number_of_shifts_performed_by_trailer[tl]];
                int shift_rank = 0;
                foreach (IRP_Roadef_Challenge_Shift_ sh in shift)
                {
                    if (sh.trailer == tl)
                    {
                        shift_performed_by_trailer[tl][shift_rank] = sh.index;
                        shift_rank = shift_rank + 1;
                    }
                }
            }


            for (int tl = 0; tl < input.trailers.Length; tl++)
            {
                int i = 1, j;

                while (i < number_of_shifts_performed_by_trailer[tl])
                {
                    int min = shift_performed_by_trailer[tl][i];
                    j = i - 1;
                    while (j >= 0 & shift[min].start < shift[shift_performed_by_trailer[tl][j]].start)
                    {
                        shift_performed_by_trailer[tl][j + 1] = shift_performed_by_trailer[tl][j];
                        j = j - 1;
                    }
                    shift_performed_by_trailer[tl][j + 1] = min;
                    i++;
                }
            }

            return shift_performed_by_trailer;
        }

        #endregion

      
        /// <summary>
        /// Main method used to perform a check of an IRP_Roadef_Challenge_Output 
        /// 
        internal static void Main(string[] args)
        {

            if (args.Length != 2)
            {
                Console.WriteLine("please specify the input and the output xml");
                Console.ReadKey();
                return;
            }

            /// <summary>
            /// Read an input xml file and an output xml file.</summary>
            ///
             

            // Deserialization  Roadef_Challenge_Instance
            TextReader reader = new StreamReader(args[0]);//XmlOutputDir + inputFile
            Debug.Assert(reader != null);

            var serializer = new XmlSerializer(typeof(IRP_Roadef_Challenge_Instance));
            Debug.Assert(serializer != null);

            var IRP_Roadef_Challenge_Instance1 = (IRP_Roadef_Challenge_Instance)serializer.Deserialize(reader);
            Debug.Assert(IRP_Roadef_Challenge_Instance1 != null);
            reader.Close();

            // Deserialization  Roadef_Challenge_Instance_Output_
            TextReader reader_ = new StreamReader(args[1]);//XmlOutputDir + output_name2
            Debug.Assert(reader != null);

            var serializer_ = new XmlSerializer(typeof(IRP_Roadef_Challenge_Output_));
            Debug.Assert(serializer != null);

            var IRP_Roadef_Challenge_output2 = (IRP_Roadef_Challenge_Output_)serializer_.Deserialize(reader_);
            Debug.Assert(IRP_Roadef_Challenge_output2 != null);
            reader_.Close();

           
            IRP_Roadef_Challenge_Checker check = new IRP_Roadef_Challenge_Checker(IRP_Roadef_Challenge_Instance1, IRP_Roadef_Challenge_output2);
        


            check.ReadAndRun();

            Console.WriteLine("\n\nPlease enter to exit...");
            Console.ReadLine();


        }

        /// <summary>
        /// Perform the checking.</summary>
        /// 
        public void ReadAndRun()
        {
            Console.WriteLine( "\n\n\n**********************************************************************" );
            Console.WriteLine( "****** IRP ROADEF/EURO 2016 CHALLENGE OUPUT CHECKER ***********************" );
            Console.WriteLine( "**********************************************************************\n\n" );

            if (checkAllOutputData())
            {
                Console.WriteLine( "\n\n\n**********************************************************************" );
                Console.WriteLine( "**********************************************************************" );
                Console.WriteLine("************************* THIS OUTPUT IS VALID ***********************");
                Console.WriteLine( "**********************************************************************" );
                Console.WriteLine( "**********************************************************************\n\n" );

                Console.WriteLine("\n\n\n**********************************************************************");
                Console.WriteLine("**********************************************************************");
                Console.WriteLine("******* Horizon = {3,4} ({4,2} days) ************************************* \n        Logistic Ratio = {0,8:0.000000}, \n        Total Shifts Cost = {1,8:0.00}, \n        Total Delivered Quantity  = {2,8}",
                   this.output.LogisticRatios, this.output.TotalShiftsCosts, this.output.DeliveredQuantities, this.input.horizon, this.input.horizon / 24);
                Console.WriteLine("**********************************************************************");
                Console.WriteLine("**********************************************************************\n\n");
            }
            else
            {
                Console.WriteLine( "\n\n\n**********************************************************************" );
                Console.WriteLine( "**********************************************************************" );
                Console.WriteLine("************************ CHECKING FAILED ************************");
                Console.WriteLine( "**********************************************************************" );
                Console.WriteLine( "**********************************************************************" );
            }

        }


        /// <summary>
        /// Check a IRP_Roadef_Challenge_Output object.</summary>
        /// 
        /// <param name="IRP_Roadef_Challenge_Instance">IRP_Roadef_Challenge_Instance linked to the IRP_Roadef_Challenge_Output.</param>
        /// <param name="IRP_Roadef_Challenge_Output">IRP_Roadef_Challenge_Output to check.</param>
        /// 
        /// <returns>True if the ouput is valid.</returns>
        /// 
        public bool runOutputChecker(IRP_Roadef_Challenge_Instance Input, IRP_Roadef_Challenge_Output_ Output)
        {
            IRP_Roadef_Challenge_Checker OutputChecker = new IRP_Roadef_Challenge_Checker(Input, Output);

            Console.WriteLine( "\n\n\n**********************************************************************" );
            Console.WriteLine( "************************* OUPUT CHECKER ***********************" );
            Console.WriteLine( "**********************************************************************\n\n" );

            bool value = OutputChecker.checkAllOutputData();

            if (value)
            {
                Console.WriteLine( "\n\n\n**********************************************************************" );
                Console.WriteLine( "**********************************************************************" );
                Console.WriteLine("************************ THIS OUTPUT IS VALID ************************");
                Console.WriteLine( "**********************************************************************" );
                Console.WriteLine( "**********************************************************************" );
            }
            else
            {
                Console.WriteLine( "\n\n\n**********************************************************************" );
                Console.WriteLine( "**********************************************************************" );
                Console.WriteLine("************************ CHECKING FAILED ************************");
                Console.WriteLine( "**********************************************************************" );
                Console.WriteLine( "**********************************************************************" );
                Debug.Assert( false );
            }

            return value;
        }

        #endregion
    }
}
