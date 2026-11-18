using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using ChicagoBuildBridge;
using Colossal;
using Colossal.AssetPipeline;
using Colossal.IO.AssetDatabase;
using Colossal.UI;
using Game;
using Game.AssetPipeline;
using Game.Prefabs;
using Game.SceneFlow;
using Game.UI.Editor;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Unity.Mathematics;
using UnityEngine;

namespace ChicagoBuildExtensions
{
    public static class Entry
    {
        static string Root;
        const string AssetName = "GPT's John Hancock's Spire by X_Bean_X";
        const string MeshName = "XBeanXJohnHancocksSpireV1";
        const string Stage = "ImportedData/XBeanXJohnHancocksSpireV1Authoring";
        const string Seed = "XBeanXJohnHancocksSpireV1Geometry";
        const float BeaconPeriod = 2.0f;
        static string Report => Path.Combine(Root, "Validation", "Native build.json");

        sealed class Factory : IPrefabFactory
        {
            public readonly SortedDictionary<int, RenderPrefab> Meshes = new SortedDictionary<int, RenderPrefab>();

            public T CreatePrefab<T>(string sourcePath, string assetName, int lodLevel) where T : PrefabBase
            {
                var prefab = PrefabBase.Create<T>(assetName);
                if (!(prefab is RenderPrefab mesh) || !assetName.StartsWith(MeshName, StringComparison.Ordinal))
                    throw new InvalidDataException("Unexpected asset in the spire import folder: " + assetName);
                Meshes.Add(lodLevel, mesh);
                return prefab;
            }
        }

        public static object Run(BridgeSystem bridge, JObject args)
        {
            var workRoot = (string)args["workRoot"];
            if (string.IsNullOrWhiteSpace(workRoot))
                return new { error = "Specify the asset project directory in workRoot." };
            Root = Path.GetFullPath(workRoot);
            if (GameManager.instance.isGameLoading || GameManager.instance.gameMode != GameMode.Editor ||
                (string)args["mode"] != "build" || File.Exists(Report))
                return new { error = "A fresh isolated Editor session is required." };
            var prefabs = bridge.World.GetExistingSystemManaged<PrefabSystem>();
            if (!prefabs.TryGetPrefab(new PrefabID(nameof(UIAssetCategoryPrefab), "PropsIndustrial"), out var category))
                return new { error = "Expected the base-game Industrial Props catalog." };
            Write(new { status = "importing" });
            Build((UIAssetCategoryPrefab)category);
            return new { status = "queued", receipt = Report };
        }

        static AnimationCurve Pulse()
        {
            var curve = new AnimationCurve(
                new Keyframe(0, 0.035f), new Keyframe(0.08f, 1.0f),
                new Keyframe(0.17f, 0.86f), new Keyframe(0.34f, 0.035f), new Keyframe(1f, 0.035f));
            curve.preWrapMode = WrapMode.Loop;
            curve.postWrapMode = WrapMode.Loop;
            return curve;
        }

        static async void Build(UIAssetCategoryPrefab category)
        {
            try
            {
                var factory = new Factory();
                var previousDatabase = AssetImportPipeline.targetDatabase;
                var previousSeed = AssetImportPipeline.importSeed;
                try
                {
                    AssetImportPipeline.targetDatabase = AssetDatabase.user;
                    AssetImportPipeline.importSeed = Seed;
                    await AssetImportPipeline.ImportPath(Root.Replace('\\', '/'), new[] { "Import" }, ImportMode.All | ImportMode.Forced,
                        convertToVT: false, prefabFactory: factory);
                }
                finally
                {
                    AssetImportPipeline.targetDatabase = previousDatabase;
                    AssetImportPipeline.importSeed = previousSeed;
                }
                if (!factory.Meshes.Keys.SequenceEqual(new[] { 0, 1, 2 }))
                    throw new InvalidDataException("Expected exactly three imported mesh LODs.");
                var mesh = factory.Meshes[0];
                var auditedMeshes = factory.Meshes.Select(pair =>
                {
                    var p = pair.Value;
                    var min = p.bounds.min;
                    var max = p.bounds.max;
                    return new { lod = pair.Key, name = p.name, triangles = p.indexCount / 3, p.vertexCount,
                        min = new[] { min.x, min.y, min.z }, max = new[] { max.x, max.y, max.z } };
                }).ToArray();
                foreach (var row in auditedMeshes)
                {
                    var expected = new[] { -1.5f, 0f, -1.5f, 1.5f, 60f, 1.5f };
                    if (row.min.Concat(row.max).Zip(expected, (a, b) => Math.Abs(a - b)).Any(v => v > 0.01f))
                        throw new InvalidDataException("Imported bounds disagree with the 60 m model: " +
                            JsonConvert.SerializeObject(row));
                }
                var lods = mesh.AddOrGetComponent<LodProperties>();
                lods.m_LodMeshes = new[] { factory.Meshes[1], factory.Meshes[2] };
                var lights = mesh.AddOrGetComponent<EmissiveProperties>();
                var foundImportedEmissive = lights.hasSingleLights;
                lights.m_SingleLights = new List<EmissiveProperties.SingleLightMapping>
                {
                    new EmissiveProperties.SingleLightMapping
                    {
                        materialId = 0,
                        purpose = EmissiveProperties.Purpose.DecorativeLight,
                        previewState = true,
                        color = Color.white,
                        colorOff = Color.black,
                        intensity = 1.8f,
                        animationIndex = 0
                    }
                };
                lights.m_AnimationCurves = new List<EmissiveProperties.AnimationProperties>
                {
                    new EmissiveProperties.AnimationProperties { m_Duration = BeaconPeriod, m_Curve = Pulse() }
                };
                foreach (var model in factory.Meshes.Values.Reverse())
                    SavePrefab(model);

                var prop = PrefabBase.Create<StaticObjectPrefab>(AssetName);
                prop.m_Meshes = new[]
                {
                    new ObjectMeshInfo { m_Mesh = mesh, m_Position = float3.zero, m_Rotation = quaternion.identity }
                };
                var placement = prop.AddComponent<PlaceableObject>();
                placement.m_ConstructionCost = 0;
                placement.m_XPReward = 0;

                var icon = AssetDatabase.user.AddAsset<ImageAsset>(AssetDataPath.Create(
                    Stage, MeshName + " Icon.png", hasExtension: true));
                using (var target = icon.GetWriteStream())
                using (var source = File.OpenRead(Path.Combine(Root, "Icon.png")))
                    source.CopyTo(target);
                icon.Save();
                var ui = prop.AddComponent<UIObject>();
                ui.m_Group = category;
                ui.m_Icon = icon.ToGlobalUri();
                ui.m_Priority = 875;

                var nameKey = "Assets.NAME[" + AssetName + "]";
                prop.AddComponent<Localization>().m_LocalizationID = nameKey;
                var locale = AssetDatabase.user.AddAsset<LocaleAsset>(AssetDataPath.Create(Stage, MeshName + "-en-US"));
                locale.SetData(new LocaleData("en-US", new Dictionary<string, string>
                {
                    [nameKey] = AssetName,
                    ["Assets.DESCRIPTION[" + AssetName + "]"] =
                        "A 60-meter rooftop broadcast mast with a pulsing red aviation beacon, conduit and junction boxes. Created by X_Bean_X."
                }, new Dictionary<string, int>()), SystemLanguage.English, "English");
                locale.Save();
                SavePrefab(prop);

                var collector = new DependencyCollector { collectRootReverseDependencies = false };
                collector.AddAsset(prop.asset);
                collector.AddAsset(icon);
                collector.AddAsset(locale);
                var assets = collector.CompileAllAssets();
                if (collector.modDependencies.Count != 0 || collector.dlcDependencies.Count != 0)
                    throw new InvalidDataException("The spire has an unexpected mod/DLC dependency.");

                Write(new { status = "packaging", foundImportedEmissive, meshes = auditedMeshes,
                    assets = assets.Select(a => a.path).ToArray() });
                var package = await PackageHelper.CreatePackage(collector);
                if (package == null || !File.Exists(package.path))
                    throw new IOException("CS2 did not produce the native package.");
                var targetPackage = Path.Combine(Root, "Package", AssetName + ".cok");
                File.Copy(package.path, targetPackage, false);
                if (File.Exists(package.path + ".cid"))
                    File.Copy(package.path + ".cid", targetPackage + ".cid", false);
                Write(new { status = "packaged", asset = AssetName, type = nameof(StaticObjectPrefab),
                    author = "X_Bean_X", path = targetPackage, editorPackage = package.path,
                    stages = new[] { Stage, "ImportedData/" + Seed }, foundImportedEmissive,
                    category = category.name, beaconPeriod = BeaconPeriod, meshes = auditedMeshes,
                    mods = collector.modDependencies, dlc = collector.dlcDependencies,
                    assets = assets.Select(a => a.path).ToArray() });
            }
            catch (Exception error)
            {
                Write(new { status = "failed", error = error.ToString() });
            }
        }

        static void SavePrefab(PrefabBase prefab)
        {
            var asset = AssetDatabase.user.AddAsset(AssetDataPath.Create(Stage, prefab.name), prefab);
            asset.Save();
        }

        static void Write(object document)
        {
            File.WriteAllText(Report + ".tmp", JsonConvert.SerializeObject(document, Formatting.Indented));
            if (File.Exists(Report)) File.Replace(Report + ".tmp", Report, null);
            else File.Move(Report + ".tmp", Report);
        }
    }
}
