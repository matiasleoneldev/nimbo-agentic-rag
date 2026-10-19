import { Chat } from "./chat";
import { dictionaries, getLanguage } from "./i18n";

export default async function Page() {
  return <Chat t={dictionaries[await getLanguage()]} />;
}
