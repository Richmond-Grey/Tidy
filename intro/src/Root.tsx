import { Composition } from "remotion";
import { BearIntro } from "./BearIntro";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="BearIntro"
      component={BearIntro}
      durationInFrames={108}
      fps={30}
      width={720}
      height={450}
    />
  );
};
