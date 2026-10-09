/** A user-gesture-enabled announcement, played at most once per navigation run. */
export class NearGoalAnnouncement {
  private context?: AudioContext;
  private buffer?: Promise<AudioBuffer>;
  private source?: AudioBufferSourceNode;
  private announced = false;
  private generation = 0;
  private failed = false;
  private readonly url: string;
  constructor(url: string) {
    this.url = url;
  }
  async enable(): Promise<void> {
    // Call from Run or Play so browsers allow audio when proximity is reached later.
    this.context ??= new AudioContext();
    const resumed = this.context.resume();
    this.buffer ??= fetch(this.url).then(async response => {
      if (!response.ok) throw Error('The “I’m near” recording could not be loaded.');
      return this.context!.decodeAudioData(await response.arrayBuffer());
    });
    await Promise.all([resumed, this.buffer]);
    if (this.failed) {
      this.failed = false;
      this.announced = false;
    }
  }
  async playIfNear(distance: number): Promise<boolean> {
    if (!Number.isFinite(distance) || distance < 0 || distance > 5 || this.announced) return false;
    this.announced = true;
    const generation = this.generation;
    try {
      await this.enable();
      if (generation !== this.generation) return false;
      this.source = this.context!.createBufferSource();
      this.source.buffer = await this.buffer!;
      this.source.connect(this.context!.destination);
      this.source.start();
      return true;
    } catch (error) {
      // A failed play can be retried by pressing Play after enabling audio.
      if (generation === this.generation) this.failed = true;
      this.buffer = undefined;
      throw error;
    }
  }
  reset(): void {
    this.generation++;
    this.announced = false;
    this.failed = false;
    this.silence();
  }
  silence(): void {
    try {
      this.source?.stop();
    } catch {/* Source may already have finished. */}
    this.source = undefined;
  }
  dispose(): void {
    this.reset();
    void this.context?.close();
    this.context = undefined;
    this.buffer = undefined;
  }
}
