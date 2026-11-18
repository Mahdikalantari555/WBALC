import { latest, type Model, type Observation, type XY } from './research';

export const sceneWidth = 1536;
export const sceneHeight = 1024;
export const sceneMetersPerUnit = 8;
export const sceneImage = '/maps/zarivar-satellite.jpg';
export const terrainImage = '/maps/zarivar-terrain.svg';

// Coordinates trace the bundled illustration, not a surveyed shoreline.
export const waterOutline: XY[] = [
  [539,92],[550,97],[560,116],[578,130],[598,147],[623,157],[649,168],[674,178],[688,192],[697,216],
  [714,232],[733,229],[759,237],[774,253],[774,273],[787,291],[788,312],[801,326],[797,346],[818,358],
  [832,369],[842,385],[835,400],[823,414],[823,433],[812,448],[826,462],[832,481],[827,499],[816,519],
  [808,540],[812,559],[823,573],[829,589],[830,608],[827,627],[836,648],[832,668],[830,683],[839,699],
  [853,716],[864,731],[870,751],[862,771],[868,788],[873,809],[884,828],[892,848],[883,857],[867,856],
  [853,846],[835,831],[821,814],[808,801],[806,783],[787,771],[791,755],[781,743],[780,726],[760,710],
  [744,701],[725,691],[718,678],[717,659],[704,647],[705,630],[690,622],[679,607],[676,590],[661,582],
  [649,569],[651,548],[636,537],[627,525],[632,509],[639,494],[648,479],[644,467],[630,454],[638,441],
  [628,427],[613,418],[605,435],[597,427],[596,417],[581,410],[572,395],[570,377],[563,357],[575,341],
  [582,324],[571,313],[574,291],[586,278],[601,273],[599,258],[596,239],[599,220],[591,205],[581,192],
  [570,175],[559,155],[551,138],[546,117],
];

export const reedOutlines: XY[][] = [
  [[551,138],[564,145],[577,166],[588,190],[601,210],[610,218],[616,244],[611,261],[601,273],[599,251],[596,236],[599,220],[589,206],[580,193],[566,170]],
  [[589,416],[592,428],[604,438],[613,420],[626,428],[636,440],[630,454],[645,471],[649,484],[639,495],[634,511],[627,511],[614,494],[616,478],[612,463],[601,449],[589,446],[587,433]],
  [[778,273],[789,277],[800,290],[803,310],[815,324],[810,337],[820,347],[838,353],[849,368],[856,383],[849,399],[834,415],[828,432],[822,439],[821,416],[836,401],[844,384],[823,364],[797,346],[800,327],[789,313],[789,292]],
  [[829,475],[843,473],[850,484],[847,500],[834,517],[825,530],[823,545],[832,561],[843,575],[843,591],[832,602],[830,584],[816,565],[808,542],[816,519],[827,497]],
  [[718,657],[719,677],[727,691],[743,701],[761,711],[780,727],[780,742],[791,755],[787,772],[804,785],[815,807],[795,799],[779,787],[771,771],[768,749],[767,731],[748,718],[729,713],[714,702],[704,688],[705,668]],
  [[864,734],[878,742],[882,759],[875,775],[884,791],[883,812],[900,829],[909,852],[897,865],[881,872],[867,864],[882,856],[890,848],[881,828],[871,808],[870,788],[865,770],[870,750]],
];

export const boundary: XY[] = [
  [463,87],[624,52],[736,80],[827,132],[904,204],[963,285],[1032,351],[1039,465],[1008,517],
  [1067,633],[1095,739],[1050,870],[960,924],[862,914],[776,870],[727,814],[649,750],[604,667],
  [561,595],[519,517],[477,437],[454,346],[466,289],[420,207],[422,136],
];

export const placeLabels: { text: string; point: XY; tone: string }[] = [
  { text: 'Zarivar Lake', point: [717, 440], tone: 'lake' },
  { text: 'Marivan', point: [1304, 808], tone: 'town' },
  { text: 'Kani Miran', point: [1003, 509], tone: 'locality' },
  { text: 'Zagros Mountains', point: [258, 310], tone: 'terrain' },
];

export function mockWaterOutline(observation: Observation, model?: Model): XY[] {
  const scale = Math.sqrt(observation.water / latest.water) * (model?.extent ?? 1);
  return waterOutline.map(([x, y]) => [720 + (x - 720) * scale, 475 + (y - 475) * scale]);
}

export function mockReedOutlines(observation: Observation, model?: Model): XY[][] {
  const edgeScale = Math.sqrt(observation.water / latest.water) * (model?.extent ?? 1);
  const reedScale = Math.sqrt(observation.vegetation / latest.vegetation) * (model?.id === 'sar' ? .78 : 1);
  return reedOutlines.map(shape => {
    const center = shape.reduce(([a, b], [x, y]) => [a + x / shape.length, b + y / shape.length], [0, 0]);
    return shape.map(([x, y]) => [
      720 + (center[0] - 720) * edgeScale + (x - center[0]) * reedScale,
      475 + (center[1] - 475) * edgeScale + (y - center[1]) * reedScale,
    ]);
  });
}

export const shapePoints = (points: XY[]) => points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

// A schematic WGS84 frame for exports and map coordinates only.
export function sceneToLonLat([x, y]: XY): [number, number] {
  const longitude = 46.058 + x * .0000885;
  const latitude = 35.572 - y * .00007195;
  return [Number(longitude.toFixed(6)), Number(latitude.toFixed(6))];
}