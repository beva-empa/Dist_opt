import mosek
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import datetime as dt
import math
import time
import cvxpy as cp
import pickle
import os
import sys
import logging
from comp_classes import *
from test_multi import *
# from visualize_results import *
from main_multi2 import *


def single_optimize(elec_storage, battery_depth, thermal_storage, CHP_Runtime, CHP_Downtime, capacities_conv,
                    capacities_stor, tech_details, storage_details, network_cap, list_techs, list_storage, demand_data,
                    hub, time_now):
    # Original boundary condition
    hub_el = 'elec_' + str(hub)
    hub_ht = 'heat_' + str(hub)

    P_Demand = demand_data.loc[time_now: time_now + dt.timedelta(hours=23), hub_el].values.tolist()
    Q_Demand = demand_data.loc[time_now: time_now + dt.timedelta(hours=23), hub_ht].values.tolist()
    Ta = demand_data.loc[time_now: time_now + dt.timedelta(hours=23), 'temp'].values.tolist()
    I_Solar = demand_data.loc[time_now: time_now + dt.timedelta(hours=23), 'solar_roof'].values.tolist()

    Rini_CHP = CHP_Runtime[hub - 1]
    Dini_CHP = CHP_Downtime[hub - 1]

    power_list = []
    heat_list = []

    cost = 0
    constr = []

    Qmax_GSHP = 0

    comp_list = []
    it = 0

    hb = hub - 1

    ex_list = []
    ch_list = []
    im_list = []
    tran_list = []
    count = 0

    for rt in range(num_hubs):
        for st in range(num_hubs):
            if st != rt:
                if rt == hb:
                    ex_list.append(count)
                    ch_list.append(1)
                    tran_list.append(trans_local(num_opt_var))
                    Pmax_tran = math.ceil(network_cap.loc[((network_cap.node1 == rt + 1) &
                                                           (
                                                                   network_cap.node2 == st + 1)), 'value'].squeeze())
                    for t in range(num_opt_var):
                        constr += [tran_list[len(tran_list) - 1].P_strt[t] >= 0,
                                   tran_list[len(tran_list) - 1].P_strt[t] <= Pmax_tran,
                                   tran_list[len(tran_list) - 1].Q_strt[t] >= 0,
                                   tran_list[len(tran_list) - 1].Q_strt[t] <= Pmax_tran]
                elif st == hb:
                    im_list.append(count)
                    ch_list.append(1)
                    tran_list.append(trans_local(num_opt_var))
                    Pmax_tran = math.ceil(network_cap.loc[((network_cap.node1 == rt + 1) &
                                                           (
                                                                   network_cap.node2 == st + 1)), 'value'].squeeze())
                    for t in range(num_opt_var):
                        constr += [tran_list[len(tran_list) - 1].P_strt[t] >= 0,
                                   tran_list[len(tran_list) - 1].P_strt[t] <= Pmax_tran,
                                   tran_list[len(tran_list) - 1].Q_strt[t] >= 0,
                                   tran_list[len(tran_list) - 1].Q_strt[t] <= Pmax_tran]
                else:
                    tran_list.append(0)
                    ch_list.append(0)

                count += 1

    for item in list_techs[hub - 1]:

        if item == 'solar_PV':
            Pmax_PV = math.ceil(capacities_conv.loc[((capacities_conv.hub == hub) & (
                    capacities_conv.tech == item)), 'value'].squeeze())
            Eff_PV = math.ceil(tech_details.loc[(tech_details.tech == item), 'eff'].squeeze()) * 0.01
            Pmin_PV = 0

            comp_list.append(PV(num_opt_var))

            power_list.append(comp_list[it].P_PV)

            for t in range(num_opt_var):
                comp_list[it].I_PV[t] = I_Solar[t] * (Pmax_PV / d_PV)
                comp_list[it].TempEff_PV[t] = 1 + ((-beta) * ((Ta[t] - Tstc) +
                                                              (Tnoct - Ta[t]) * (I_Solar[t] / 0.8)))

            for t in range(num_opt_var):
                constr += [comp_list[it].P_PV[t] >= 0,
                           comp_list[it].P_PV[t] <= (comp_list[it].b_PV[t] * Eff_PV *
                                                     comp_list[it].TempEff_PV[t] * comp_list[it].I_PV[t])]

            it = it + 1

        elif item == 'solar_PVT':

            Pmax_PVT = math.ceil(capacities_conv.loc[((capacities_conv.hub == hub) & (
                    capacities_conv.tech == item)), 'value'].squeeze())
            Eff_PVT = tech_details.loc[(tech_details.tech == item), 'outshare'].squeeze()
            list1 = Eff_PVT.split(",")
            li1 = []
            for t in list1:
                li1.append(float(t))

            PEff_PVT = li1[0]
            QEff_PVT = li1[1]

            Eff_PVT = tech_details.loc[(tech_details.tech == item), 'eff'].squeeze() * 0.01

            comp_list.append(PVT(num_opt_var))

            power_list.append(comp_list[it].P_PVT)
            heat_list.append(comp_list[it].Q_PVT)

            for t in range(num_opt_var):
                comp_list[it].I_PVT[t] = I_Solar[t] * (Pmax_PVT / d_PVT)
                comp_list[it].TempEff_PVT[t] = 1 + ((-beta) * ((Ta[t] - Tstc) +
                                                               (Tnoct - Ta[t]) * (I_Solar[t] / 0.8)))

            for t in range(num_opt_var):
                constr += [comp_list[it].P_PVT[t] >= 0, comp_list[it].Q_PVT[t] >= 0,
                           comp_list[it].Out_PVT[t] <= (comp_list[it].b_PVT[t] * Eff_PVT *
                                                        comp_list[it].TempEff_PVT[t] * comp_list[it].I_PVT[t]),
                           comp_list[it].P_PVT[t] == PEff_PVT * comp_list[it].Out_PVT[t],
                           comp_list[it].Q_PVT[t] == QEff_PVT * comp_list[it].Out_PVT[t]]

            it = it + 1

        elif item == 'Gas_CHP_unit_1':

            Pmax_mCHP = math.ceil(capacities_conv.loc[((capacities_conv.hub == hub) & (
                    capacities_conv.tech == item)), 'value'].squeeze())
            Pmin_mCHP = 0
            Eff_mCHP = tech_details.loc[(tech_details.tech == item), 'outshare'].squeeze()

            list2 = Eff_mCHP.split(",")
            li = []
            for k in list2:
                li.append(float(k))
            PEff_mCHP = li[0]
            QEff_mCHP = li[1]
            Eff_mCHP = tech_details.loc[(tech_details.tech == item), 'eff'].squeeze() * 0.01

            comp_list.append(mCHP(num_opt_var))

            power_list.append(comp_list[it].P_mCHP)
            heat_list.append(comp_list[it].Q_mCHP)

            for t in range(num_opt_var):
                cost += comp_list[it].C_mCHP[t]
                constr += [comp_list[it].Out_mCHP[t] >= comp_list[it].b_mCHP[t] * Pmin_mCHP,
                           comp_list[it].Out_mCHP[t] <= comp_list[it].b_mCHP[t] * Pmax_mCHP,
                           comp_list[it].P_mCHP[t] == PEff_mCHP * comp_list[it].Out_mCHP[t],
                           comp_list[it].Q_mCHP[t] == QEff_mCHP * comp_list[it].Out_mCHP[t],
                           comp_list[it].C_mCHP[t] == C_Fuel * comp_list[it].F_mCHP[t],
                           comp_list[it].F_mCHP[t] == comp_list[it].P_mCHP[t] / Eff_mCHP]

            it = it + 1

        elif item == 'Gas_CHP_unit_2':

            Pmax_CHP = math.ceil(capacities_conv.loc[((capacities_conv.hub == hub) & (
                    capacities_conv.tech == item)), 'value'].squeeze())
            Pmin_CHP = 0
            Eff_CHP = tech_details.loc[(tech_details.tech == item), 'outshare'].squeeze()
            list2 = Eff_CHP.split(",")
            li = []
            for m in list2:
                li.append(float(m))
            PEff_CHP = li[0]
            QEff_CHP = li[1]
            Eff_CHP = tech_details.loc[(tech_details.tech == item), 'eff'].squeeze() * 0.01
            CHP_points = CHP_operation(Pmax_CHP, Eff_CHP, PEff_CHP, QEff_CHP, n_CHP, min_cap_CHP)
            CHP_fuelcap = Pmax_CHP / Eff_CHP

            P11_CHP = CHP_points[1][0]
            P12_CHP = CHP_points[1][0]
            P13_CHP = CHP_points[1][3]
            P14_CHP = CHP_points[1][4]
            P21_CHP = CHP_points[1][0]
            P22_CHP = CHP_points[1][1]
            P23_CHP = CHP_points[1][2]
            P24_CHP = CHP_points[1][3]

            Q11_CHP = CHP_points[0][0]
            Q12_CHP = CHP_points[0][0]
            Q13_CHP = CHP_points[0][3]
            Q14_CHP = CHP_points[0][4]
            Q21_CHP = CHP_points[0][0]
            Q22_CHP = CHP_points[0][1]
            Q23_CHP = CHP_points[0][2]
            Q24_CHP = CHP_points[0][3]

            comp_list.append(CHP(num_opt_var))

            power_list.append(comp_list[it].P_CHP)
            heat_list.append(comp_list[it].Q_CHP)

            constr += [comp_list[it].ysum_CHP[0] == comp_list[it].yon_CHP[0],
                       comp_list[it].zsum_CHP[0] == comp_list[it].zoff_CHP[0],
                       comp_list[it].R_CHP[0] == (Rini_CHP + 1) * comp_list[it].b_CHP[0],
                       comp_list[it].D_CHP[0] == (Dini_CHP + 1) * (1 - comp_list[it].b_CHP[0])]

            if Rini_CHP == 0:
                constr += [comp_list[it].zoff_CHP[0] == 0, comp_list[it].yon_CHP[0] == comp_list[it].b_CHP[0]]
            elif Dini_CHP == 0:
                constr += [comp_list[it].zoff_CHP[0] == 1 - comp_list[it].b_CHP[0], comp_list[it].yon_CHP[0] == 0]

            for t in range(num_opt_var):

                cost += comp_list[it].C_CHP[t]
                constr += [comp_list[it].P_CHP[t] <= Pmax_CHP * 10 * comp_list[it].b_CHP[t],
                           comp_list[it].Q_CHP[t] <= Pmax_CHP * 10 * comp_list[it].b_CHP[t],
                           comp_list[it].P_CHP[t] >= Pmin_CHP * comp_list[it].b_CHP[t],
                           comp_list[it].Q_CHP[t] >= Pmin_CHP * comp_list[it].b_CHP[t],
                           comp_list[it].P_CHP[t] == (
                                   comp_list[it].w11_CHP[t] * P11_CHP + comp_list[it].w12_CHP[t] * P12_CHP +
                                   comp_list[it].w13_CHP[t] * P13_CHP + comp_list[it].w14_CHP[t] * P14_CHP +
                                   comp_list[it].w21_CHP[t] * P21_CHP + comp_list[it].w22_CHP[t] * P22_CHP +
                                   comp_list[it].w23_CHP[t] * P23_CHP + comp_list[it].w24_CHP[t] * P24_CHP),
                           comp_list[it].Q_CHP[t] == (
                                   comp_list[it].w11_CHP[t] * Q11_CHP + comp_list[it].w12_CHP[t] * Q12_CHP +
                                   comp_list[it].w13_CHP[t] * Q13_CHP + comp_list[it].w14_CHP[t] * Q14_CHP +
                                   comp_list[it].w21_CHP[t] * Q21_CHP + comp_list[it].w22_CHP[t] * Q22_CHP +
                                   comp_list[it].w23_CHP[t] * Q23_CHP + comp_list[it].w24_CHP[t] * Q24_CHP),
                           comp_list[it].b1_CHP[t] + comp_list[it].b2_CHP[t] == comp_list[it].b_CHP[t],
                           comp_list[it].w11_CHP[t] + comp_list[it].w12_CHP[t] + comp_list[it].w13_CHP[t] +
                           comp_list[it].w14_CHP[t] == comp_list[it].b1_CHP[t],
                           comp_list[it].w21_CHP[t] + comp_list[it].w22_CHP[t] + comp_list[it].w23_CHP[t] +
                           comp_list[it].w24_CHP[t] == comp_list[it].b2_CHP[t],
                           comp_list[it].w11_CHP[t] >= 0, comp_list[it].w12_CHP[t] >= 0,
                           comp_list[it].w13_CHP[t] >= 0, comp_list[it].w14_CHP[t] >= 0,
                           comp_list[it].w21_CHP[t] >= 0, comp_list[it].w22_CHP[t] >= 0,
                           comp_list[it].w23_CHP[t] >= 0, comp_list[it].w24_CHP[t] >= 0,
                           comp_list[it].w11_CHP[t] <= 1, comp_list[it].w12_CHP[t] <= 1,
                           comp_list[it].w13_CHP[t] <= 1, comp_list[it].w14_CHP[t] <= 1,
                           comp_list[it].w21_CHP[t] <= 1, comp_list[it].w22_CHP[t] <= 1,
                           comp_list[it].w23_CHP[t] <= 1, comp_list[it].w24_CHP[t] <= 1,
                           comp_list[it].yon_CHP[t] + comp_list[it].zoff_CHP[t] <= 1,
                           comp_list[it].C_CHP[t] == C_Fuel * comp_list[it].F_CHP[t],
                           comp_list[it].F_CHP[t] == comp_list[it].P_CHP[t] / Eff_CHP]
                if t >= 1:
                    constr += [comp_list[it].P_CHP[t] <= (comp_list[it].P_CHP[t - 1] + 0.5 * Pmax_CHP *
                                                          (comp_list[it].b_CHP[t - 1] + comp_list[it].yon_CHP[t])),
                               comp_list[it].P_CHP[t] >= (comp_list[it].P_CHP[t - 1] - 0.5 * Pmax_CHP *
                                                          (comp_list[it].b_CHP[t] + comp_list[it].zoff_CHP[t])),
                               comp_list[it].Q_CHP[t] <= (comp_list[it].Q_CHP[t - 1] + 0.5 * Pmax_CHP *
                                                          (comp_list[it].b_CHP[t - 1] + comp_list[it].yon_CHP[t])),
                               comp_list[it].Q_CHP[t] >= (comp_list[it].Q_CHP[t - 1] - 0.5 * Pmax_CHP *
                                                          (comp_list[it].b_CHP[t] + comp_list[it].zoff_CHP[t])),
                               comp_list[it].yon_CHP[t] - comp_list[it].zoff_CHP[t] == (comp_list[it].b_CHP[t] -
                                                                                        comp_list[it].b_CHP[t - 1])]

                # min up time constraints
                if UPmin_CHP > 0:
                    if t >= UPmin_CHP:
                        constr += [comp_list[it].b_CHP[t] >= comp_list[it].ysum_CHP[t],
                                   comp_list[it].ysum_CHP[t] == (comp_list[it].ysum_CHP[t - 1] -
                                                                 comp_list[it].yon_CHP[t - UPmin_CHP] +
                                                                 comp_list[it].yon_CHP[t])]

                    elif 1 <= t < UPmin_CHP:
                        constr += [comp_list[it].b_CHP[t] >= comp_list[it].ysum_CHP[t],
                                   comp_list[it].ysum_CHP[t] == (comp_list[it].ysum_CHP[t - 1] +
                                                                 comp_list[it].yon_CHP[t])]

                    if 0 < Rini_CHP < UPmin_CHP:
                        if t < (UPmin_CHP - Rini_CHP):
                            constr += [comp_list[it].b_CHP[t] == 1,
                                       comp_list[it].yon_CHP[t] == 0, comp_list[it].zoff_CHP[t] == 0]

                    elif Rini_CHP >= UPmin_CHP:
                        if t == 0:
                            constr += [comp_list[it].zoff_CHP[t] == 1 - comp_list[it].b_CHP[t],
                                       comp_list[it].yon_CHP[t] == 0]

                if DNmin_CHP > 0:

                    if t >= DNmin_CHP:
                        constr += [(1 - comp_list[it].b_CHP[t]) >= comp_list[it].zsum_CHP[t],
                                   comp_list[it].zsum_CHP[t] == (comp_list[it].zsum_CHP[t - 1] -
                                                                 comp_list[it].zoff_CHP[t - DNmin_CHP] +
                                                                 comp_list[it].zoff_CHP[t])]

                    if 1 <= t < DNmin_CHP:
                        constr += [(1 - comp_list[it].b_CHP[t]) >= comp_list[it].zsum_CHP[t],
                                   comp_list[it].zsum_CHP[t] == (comp_list[it].zsum_CHP[t - 1] +
                                                                 comp_list[it].zoff_CHP[t])]

                    if 0 < Dini_CHP < DNmin_CHP:
                        if t < (DNmin_CHP - Dini_CHP):
                            constr += [comp_list[it].b_CHP[t] == 0, comp_list[it].yon_CHP[t] == 0,
                                       comp_list[it].zoff_CHP[t] == 0]

                    elif Dini_CHP >= DNmin_CHP:
                        if t == 0:
                            constr += [comp_list[it].zoff_CHP[t] == 0,
                                       comp_list[it].yon_CHP[t] == comp_list[it].b_CHP[t]]

            it = it + 1

        elif item == 'GSHP_1' or item == 'GSHP_2':

            Qmax_GSHP = math.ceil(capacities_conv.loc[((capacities_conv.hub == hub) &
                                                       (capacities_conv.tech == item)), 'value'].squeeze())
            Qmin_GSHP = 0

            comp_list.append(GSHP(num_opt_var))

            power_list.append(-comp_list[it].P_GSHP)
            heat_list.append(comp_list[it].Q_GSHP)

            for t in range(num_opt_var):
                constr += [comp_list[it].Q_GSHP[t] <= comp_list[it].b_GSHP[t] * Qmax_GSHP,
                           comp_list[it].Q_GSHP[t] >= comp_list[it].b_GSHP[t] * Qmin_GSHP,
                           comp_list[it].Q_GSHP[t] == comp_list[it].P_GSHP[t] * COP]

            it = it + 1

        elif item == 'gas_boiler_1' or item == 'gas_boiler_2':

            Qmax_GB = math.ceil(capacities_conv.loc[((capacities_conv.hub == hub) &
                                                     (capacities_conv.tech == item)), 'value'].squeeze())
            Qmin_GB = 0

            x0_GB = 0
            x1_GB = 0.25 * Qmax_GB
            x2_GB = 0.5 * Qmax_GB
            x3_GB = 0.75 * Qmax_GB
            x4_GB = Qmax_GB

            Eff1_GB = 0.01 * (21.49 + (182.18 * (1 / 4)) + ((-120.67) * (1 / 4) ** 2))
            Eff2_GB = 0.01 * (21.49 + (182.18 * (2 / 4)) + ((-120.67) * (2 / 4) ** 2))
            Eff3_GB = 0.01 * (21.49 + (182.18 * (3 / 4)) + ((-120.67) * (3 / 4) ** 2))
            Eff4_GB = 0.01 * (21.49 + (182.18 * (4 / 4)) + ((-120.67) * (4 / 4) ** 2))

            comp_list.append(GB(num_opt_var))

            heat_list.append(comp_list[it].Q_GB)

            for t in range(num_opt_var):
                cost += comp_list[it].C_GB[t]
                constr += [comp_list[it].Q_GB[t] <= comp_list[it].b_GB[t] * Qmax_GB,
                           comp_list[it].Q_GB[t] >= comp_list[it].b_GB[t] * Qmin_GB,
                           comp_list[it].Q_GB[t] == (comp_list[it].w1_GB[t] * x1_GB +
                                                     comp_list[it].w2_GB[t] * x2_GB +
                                                     comp_list[it].w3_GB[t] * x3_GB +
                                                     comp_list[it].w4_GB[t] * x4_GB),
                           (comp_list[it].b1_GB[t] + comp_list[it].b2_GB[t] +
                            comp_list[it].b3_GB[t] + comp_list[it].b4_GB[t]) == comp_list[it].b_GB[t],
                           (comp_list[it].w0_GB[t] + comp_list[it].w1_GB[t] + comp_list[it].w2_GB[t] +
                            comp_list[it].w3_GB[t] + comp_list[it].w4_GB[t]) == comp_list[it].b_GB[t],
                           comp_list[it].w0_GB[t] <= comp_list[it].b1_GB[t],
                           comp_list[it].w1_GB[t] <= comp_list[it].b1_GB[t] + comp_list[it].b2_GB[t],
                           comp_list[it].w2_GB[t] <= comp_list[it].b3_GB[t] + comp_list[it].b2_GB[t],
                           comp_list[it].w3_GB[t] <= comp_list[it].b3_GB[t] + comp_list[it].b4_GB[t],
                           comp_list[it].w4_GB[t] <= comp_list[it].b4_GB[t],
                           comp_list[it].w0_GB[t] >= 0, comp_list[it].w1_GB[t] >= 0, comp_list[it].w2_GB[t] >= 0,
                           comp_list[it].w3_GB[t] >= 0, comp_list[it].w4_GB[t] >= 0,
                           comp_list[it].w0_GB[t] <= 1, comp_list[it].w1_GB[t] <= 1, comp_list[it].w2_GB[t] <= 1,
                           comp_list[it].w3_GB[t] <= 1, comp_list[it].w4_GB[t] <= 1,
                           comp_list[it].C_GB[t] == C_Fuel * comp_list[it].F_GB[t],
                           comp_list[it].F_GB[t] == (comp_list[it].w1_GB[t] * (x1_GB / Eff1_GB) +
                                                     comp_list[it].w2_GB[t] * (x2_GB / Eff2_GB) +
                                                     comp_list[it].w3_GB[t] * (x3_GB / Eff3_GB) +
                                                     comp_list[it].w4_GB[t] * (x4_GB / Eff4_GB))]

            it = it + 1

    for item in list_storage[hub - 1]:

        if item == 'heat_storage':

            Qmax_Storage = capacities_stor.loc[((capacities_stor.hub == hub) &
                                                (capacities_stor.tech == item)), 'value'].squeeze()
            Eff_Storage = storage_details.loc[(storage_details.tech == item), 'stateff'].squeeze()
            Eff_StorageCh = storage_details.loc[(storage_details.tech == item), 'cyceff'].squeeze()
            Eff_StorageDc = Eff_StorageCh

            comp_list.append(Heat_Storage(num_opt_var))

            constr += [comp_list[it].Q_StorageTot[0] == (Eff_Storage * thermal_storage[hub - 1] +
                                                         Eff_StorageCh * comp_list[it].Q_StorageCh[0] -
                                                         Eff_StorageDc * comp_list[it].Q_StorageDc[0])]

            heat_list.append(comp_list[it].Q_StorageDc)
            heat_list.append(-comp_list[it].Q_StorageCh)

            for t in range(num_opt_var):

                constr += [comp_list[it].Q_StorageCh[t] >= 0,
                           comp_list[it].Q_StorageCh[t] <= BigM * comp_list[it].b_StorageCh[t],
                           comp_list[it].Q_StorageDc[t] >= 0,
                           comp_list[it].Q_StorageDc[t] <= BigM * comp_list[it].b_StorageDc[t],
                           comp_list[it].Q_StorageTot[t] >= 0.2 * Qmax_Storage,
                           comp_list[it].Q_StorageTot[t] <= Qmax_Storage,
                           comp_list[it].b_StorageCh[t] + comp_list[it].b_StorageDc[t] == 1,
                           comp_list[it].b_StorageCh[t] >= 0, comp_list[it].b_StorageDc[t] >= 0,
                           comp_list[it].b_StorageCh[t] <= 1, comp_list[it].b_StorageDc[t] <= 1]
                if t >= 1:
                    constr += [comp_list[it].Q_StorageTot[t] == (Eff_Storage * comp_list[it].Q_StorageTot[t - 1] +
                                                                 Eff_StorageCh * comp_list[it].Q_StorageCh[t] -
                                                                 Eff_StorageDc * comp_list[it].Q_StorageDc[t])]

            it = it + 1

        elif item == 'Battery':

            Pmax_Battery = capacities_stor.loc[((capacities_stor.hub == hub) &
                                                (capacities_stor.tech == item)), 'value'].squeeze()
            Pmin_Battery = 0
            Eff_Battery = storage_details.loc[(storage_details.tech == item), 'stateff'].squeeze()
            Eff_BatteryCh = storage_details.loc[(storage_details.tech == item), 'cyceff'].squeeze()
            Eff_BatteryDc = Eff_BatteryCh

            comp_list.append(Elec_Storage(num_opt_var))

            power_list.append(comp_list[it].P_BatteryDc)
            power_list.append(-comp_list[it].P_BatteryCh)

            constr += [comp_list[it].P_BatteryTot[0] == (Eff_Battery * elec_storage[hub - 1] +
                                                         Eff_BatteryCh * comp_list[it].P_BatteryCh[0] -
                                                         (1 / Eff_BatteryDc) * comp_list[it].P_BatteryDc[0])]

            for t in range(num_opt_var):

                constr += [comp_list[it].P_BatteryTot[t] >= 0.2 * Pmax_Battery,
                           comp_list[it].P_BatteryTot[t] <= 0.8 * Pmax_Battery,
                           comp_list[it].P_BatteryCh[t] >= 0,
                           comp_list[it].P_BatteryCh[t] <= BigM * comp_list[it].b_BatteryCh[t],
                           comp_list[it].P_BatteryDc[t] >= 0,
                           comp_list[it].P_BatteryDc[t] <= BigM * comp_list[it].b_BatteryDc[t],
                           comp_list[it].b_BatteryCh[t] + comp_list[it].b_BatteryDc[t] == 1]

                if t >= 1:
                    constr += [
                        comp_list[it].P_BatteryTot[t] == (Eff_Battery * comp_list[it].P_BatteryTot[t - 1] +
                                                          Eff_BatteryCh * comp_list[it].P_BatteryCh[t] -
                                                          (1 / Eff_BatteryDc) * comp_list[it].P_BatteryDc[t])]

            it = it + 1

    R_GridOut = demand_data.loc[time_now: time_now + dt.timedelta(hours=23), 'el_tariff'].values.tolist()
    R_GridIn = demand_data.loc[time_now: time_now + dt.timedelta(hours=23), 'feed_in_tariff'].values.tolist()

    comp_list.append(Elec_Grid(num_opt_var))
    power_list.append(comp_list[it].P_GridOut)
    power_list.append(-comp_list[it].P_GridIn)

    for idx in range(len(ex_list)):
        power_list.append(-tran_list[int(ex_list[idx])].P_strt)
        heat_list.append(-tran_list[int(ex_list[idx])].Q_strt)
        for t in range(num_opt_var):
            cost += (0.01 * tran_list[int(ex_list[idx])].P_strt[t] - 0.2 * tran_list[int(ex_list[idx])].P_strt[t])
            cost += (0.01 * tran_list[int(ex_list[idx])].Q_strt[t] - 0.2 * tran_list[int(ex_list[idx])].Q_strt[t])

    for idx in range(len(im_list)):
        power_list.append(tran_list[int(im_list[idx])].P_strt * 0.95)
        heat_list.append(tran_list[int(im_list[idx])].Q_strt * 0.90)
        for t in range(num_opt_var):
            cost += (0.2 * tran_list[int(im_list[idx])].P_strt[t])
            cost += (0.2 * tran_list[int(im_list[idx])].Q_strt[t])

    if len(power_list) < 24:
        t = len(power_list)
        while t <= 23:
            power_list.append([0] * num_opt_var)
            t = t + 1

    if len(heat_list) < 24:
        t = len(heat_list)
        while t <= 23:
            heat_list.append([0] * num_opt_var)
            t = t + 1

    for t in range(num_opt_var):
        # Demand
        cost += comp_list[it].C_Grid[t] + (cp.huber(cp.norm(comp_list[it].P_Slack[t]), P_delta) +
                                           cp.huber(cp.norm(comp_list[it].Q_Slack[t]), Q_delta))

        constr += [P_Demand[t] == (power_list[0][t] + power_list[1][t] + power_list[2][t] + power_list[3][t] +
                                   power_list[4][t] + power_list[5][t] + power_list[6][t] + power_list[7][t] +
                                   power_list[8][t] + power_list[9][t] + power_list[10][t] + power_list[11][t] +
                                   power_list[12][t] + power_list[13][t] + power_list[14][t] + power_list[15][t] +
                                   power_list[16][t] + power_list[17][t] + power_list[18][t] + power_list[19][t] +
                                   power_list[20][t] + power_list[21][t] + power_list[22][t] + power_list[23][t]),
                   Q_Demand[t] == (heat_list[0][t] + heat_list[1][t] + heat_list[2][t] + heat_list[3][t] +
                                   heat_list[4][t] + heat_list[5][t] + heat_list[6][t] + heat_list[7][t] +
                                   heat_list[8][t] + heat_list[9][t] + heat_list[10][t] + heat_list[11][t] +
                                   heat_list[12][t] + heat_list[13][t] + heat_list[14][t] + heat_list[15][t] +
                                   heat_list[16][t] + heat_list[17][t] + heat_list[18][t] + heat_list[19][t] +
                                   heat_list[20][t] + heat_list[21][t] + heat_list[22][t] + heat_list[23][t]),
                   comp_list[it].b_GridIn[t] + comp_list[it].b_GridOut[t] <= 1,
                   comp_list[it].P_GridIn[t] >= 0, comp_list[it].P_GridIn[t] <= BigM * comp_list[it].b_GridIn[t],
                   comp_list[it].P_GridOut[t] >= 0, comp_list[it].P_GridOut[t] <= BigM * comp_list[it].b_GridOut[t],
                   comp_list[it].C_Grid[t] == (R_GridOut[t] * comp_list[it].P_GridOut[t] -
                                               R_GridIn[t] * comp_list[it].P_GridIn[t]),
                   comp_list[it].P_Slack[t] >= 0, comp_list[it].Q_Slack[t] >= 0]

        # Solve with mosek or Gurobi

    problem = cp.Problem(cp.Minimize(cost), constr)
    problem.solve(solver=cp.MOSEK, verbose=True, save_file='opt_diagnosis.opf',
                  mosek_params={mosek.iparam.intpnt_solve_form: mosek.solveform.dual,
                                mosek.dparam.optimizer_max_time: 500.0})

    opt_stat = problem.status
    opt_val = problem.value
    opt_time = problem.solver_stats
    print(f"Status:{opt_stat}, with Value:{opt_val:.2f}")

    power_tot = [0] * num_opt_var
    power_out = [0] * num_opt_var
    power_cost = [0] * num_opt_var

    heat_tot = [0] * num_opt_var
    heat_out = [0] * num_opt_var
    heat_cost = [0] * num_opt_var

    it = 0
    for item in list_techs[hub - 1]:

        if item == 'solar_PV':
            for t in range(num_opt_var):
                power_tot[t] += comp_list[it].P_PV.value[t]
                power_cost[t] += 0
            it = it + 1

        if item == 'solar_PVT':
            for t in range(num_opt_var):
                power_tot[t] += comp_list[it].P_PVT.value[t]
                power_cost[t] += 0
                heat_tot[t] += comp_list[it].Q_PVT.value[t]
                heat_cost[t] += 0
            it = it + 1

        if item == 'Gas_CHP_unit_1':
            for t in range(num_opt_var):
                power_tot[t] += comp_list[it].P_mCHP.value[t]
                power_cost[t] += (comp_list[it].C_mCHP.value[t] * comp_list[it].P_mCHP.value[t] /
                                  (comp_list[it].P_mCHP.value[t] + comp_list[it].Q_mCHP.value[t]))
                heat_tot[t] += comp_list[it].Q_mCHP.value[t]
                heat_cost[t] += (comp_list[it].C_mCHP.value[t] * comp_list[it].Q_mCHP.value[t] /
                                 (comp_list[it].P_mCHP.value[t] + comp_list[it].Q_mCHP.value[t]))
            it = it + 1

        if item == 'Gas_CHP_unit_2':

            for t in range(num_opt_var):
                power_tot[t] += comp_list[it].P_CHP.value[t]
                power_cost[t] += (comp_list[it].C_CHP.value[t] * comp_list[it].P_CHP.value[t] /
                                  (comp_list[it].P_CHP.value[t] + comp_list[it].Q_CHP.value[t]))
                heat_tot[t] += comp_list[it].Q_CHP.value[t]
                heat_cost[t] += (comp_list[it].C_CHP.value[t] * comp_list[it].Q_CHP.value[t] /
                                 (comp_list[it].P_CHP.value[t] + comp_list[it].Q_CHP.value[t]))
            it = it + 1

        if item == 'GSHP_1' or item == 'GSHP_2':
            for t in range(num_opt_var):
                power_tot[t] += 0
                power_cost[t] += 0
                heat_tot[t] += comp_list[it].Q_GSHP.value[t]
                heat_cost[t] += 0

            it = it + 1

        if item == 'gas_boiler_1' or item == 'gas_boiler_2':
            for t in range(num_opt_var):
                power_tot[t] += 0
                power_cost[t] += 0
                heat_tot[t] += comp_list[it].Q_GB.value[t]
                heat_cost[t] += comp_list[it].C_GB.value[t]

            it = it + 1

    for t in range(num_opt_var):
        if power_tot[t] != 0:
            power_out[t] = power_cost[t] / power_tot[t]
        elif power_tot[t] == 0:
            power_out[t] = R_GridOut[t]

        if power_tot[t] != 0 and power_out[t] == 0:
            power_out[t] = 0.05

    for item in list_storage[hub - 1]:

        if item == 'GSHP_1' or item == 'GSHP_2':
            for t in range(num_opt_var):
                heat_cost[t] += comp_list[it].P_GSHP.value[t] * power_out[t]

    for t in range(num_opt_var):
        if heat_tot[t] != 0:
            heat_out[t] = heat_cost[t] / heat_tot[t]
        elif heat_tot[t] == 0:
            heat_out[t] = R_GridOut[t]

        if heat_out[t] <= 0.005 and heat_tot[t] != 0:
            heat_out[t] = 0.05

    print('run complete')

    return power_out, heat_out
