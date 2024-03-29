import json
import os
import urllib.request
from . import base
from . import rootgen
from ROOT import gROOT


class JsRootFairyTest(base.BaseIntegrationTest):
    @classmethod
    def setUpClass(cls):
        super(JsRootFairyTest, cls).setUpClass()
        (cls.filename, cls.run_number, cls.dataset) = cls.prepareIndex(
            {
                "/DQMData/Run 1/Pixel/Run summary/AdditionalPixelErrors": [
                    {"name": "FedChNErr", "gen": rootgen.TH1F},
                    {"name": "FedChLErr", "gen": rootgen.TH2F},
                    {"name": "FedETypeNErr", "gen": rootgen.TH2F},
                ],
                "/DQMData/Run 283560/Pixel/Run summary/AdditionalPixelErrors/FED_0": [
                    {"name": "FedETypeNErr_siPixelDigis_0", "gen": rootgen.TH1F},
                ],
                "/DQMData/Run 1/Pixel/Run summary": [
                    {"name": "averageDigiOccupancy", "gen": rootgen.TProfile}
                ],
                "/DQMData/Run 1/Pixel/Run summary/Barrel": [
                    {"name": "SUMOFF_charge_OnTrack_Barrel", "gen": rootgen.TH1F},
                    {"name": "SUMOFF_nclusters_OnTrack_Barrel", "gen": rootgen.TH1F},
                    {"name": "SUMOFF_size_OnTrack_Barrel", "gen": rootgen.TH1F},
                ],
                "/DQMData/Run 1/Pixel/Run summary/Endcap": [
                    {"name": "SUMOFF_charge_OnTrack_Endcap", "gen": rootgen.TH1F},
                    {"name": "SUMOFF_nclusters_OnTrack_Endcap", "gen": rootgen.TH1F},
                    {"name": "SUMOFF_size_OnTrack_Endcap", "gen": rootgen.TH1F},
                ],
            },
            dataset="JsRootFairyTest",
        )

    def test_TH1F(self):
        response = self.fetch_histogram("Pixel/AdditionalPixelErrors/FedChNErr")

        self.assertEqual("TH1F", response["_typename"])
        self.assertEqual("FedChNErr", response["fName"])
        self.assertEqual("FedChNErr", response["fTitle"])

    def test_TH2F(self):
        response = self.fetch_histogram("Pixel/AdditionalPixelErrors/FedChLErr")

        self.assertEqual("TH2F", response["_typename"])
        self.assertEqual("FedChLErr", response["fName"])
        self.assertEqual("FedChLErr", response["fTitle"])

    def test_TProfile(self):
        response = self.fetch_histogram("Pixel/averageDigiOccupancy")

        self.assertEqual("TProfile", response["_typename"])
        self.assertEqual("averageDigiOccupancy", response["fName"])
        self.assertEqual("averageDigiOccupancy", response["fTitle"])

    def test_exactJSON(self):
        # The fixed expected json output is dependant on ROOT version.
        fixed_json_path = (
            os.path.dirname(os.path.realpath(__file__))
            + "/jsrootfairy_FedChNErr_6.28.08.json"
        )
        with open(fixed_json_path) as fixed_json_file:
            expected_json = json.load(fixed_json_file)

        response = self.fetch_histogram("Pixel/AdditionalPixelErrors/FedChNErr")

        root_version = gROOT.GetVersion()
        self.assertDictEqual(
            expected_json,
            response,
            "%s is not compatible with current ROOT version %s"
            % (fixed_json_path, root_version),
        )

    def fetch_histogram(self, name):
        histogram_url = "%sjsrootfairy/archive/%d%s/%s" % (
            self.base_url,
            self.run_number,
            self.dataset,
            name,
        )
        histogram_response = urllib.request.urlopen(histogram_url)
        histogram_content = histogram_response.read()
        print(
            "Histogram fetched from %s with status %d"
            % (histogram_url, histogram_response.getcode())
        )
        self.assertEqual(
            histogram_response.getcode(),
            200,
            "Request failed. Status code received was not 200",
        )
        histogram_json = json.loads(histogram_content)
        return histogram_json
